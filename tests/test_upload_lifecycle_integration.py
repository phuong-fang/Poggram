import os
import threading
import time

import pytest

import shared
import store
import telegram_client
from tests.conftest import isolated_store

@pytest.fixture(autouse=True)
def _clean_upload_state():

    def _reset():
        with shared.uploads_lock:
            shared.uploads.clear()
            shared.upload_cancel_tokens.clear()
            shared.upload_retry_info.clear()
        with shared.hashes_in_progress_lock:
            shared.hashes_in_progress.clear()

    _reset()
    yield

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with shared.uploads_lock:
            busy = any(e.get("status") == "uploading" for e in shared.uploads.values())
        if not busy:
            break
        time.sleep(0.02)
    _reset()

def _wait_until_settled(upload_id, isolated_store, timeout=5.0):

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if isolated_store.find_pending_upload(upload_id) is None:
            return True
        time.sleep(0.02)
    return False

@pytest.fixture
def source_file(tmp_path):
    p = tmp_path / "clip.bin"
    p.write_bytes(b"x" * 4096)
    return str(p)

def _wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False

def _fake_transfer(monkeypatch, chat_id=-100, chunks=None, on_call=None):

    chunks = chunks or [{"message_id": 11, "size_bytes": 4096}]

    def _upload(*args, **kwargs):
        if on_call:
            on_call(kwargs)
        progress = kwargs.get("on_progress")
        if progress:
            progress(0, 1, 2048)
            progress(1, 1, 4096)
        return chat_id, chunks

    monkeypatch.setattr(telegram_client, "upload_file_parallel", _upload)
    monkeypatch.setattr(telegram_client, "upload_file", _upload)
    monkeypatch.setattr(telegram_client, "require_archive_chat", lambda: chat_id)
    return chunks

def test_upload_runs_through_to_a_vault_record(source_file, monkeypatch, isolated_store):
    _fake_transfer(monkeypatch)
    done = []
    upload_id = shared.start_background_upload(
        source_file, "clip.bin", None, 1_900_000_000, on_done=done.append)

    assert _wait_for(lambda: shared.uploads.get(upload_id, {}).get("status") == "done"), \
        shared.uploads.get(upload_id)
    entry = shared.uploads[upload_id]
    assert entry["bytes_done"] == entry["bytes_total"] == 4096
    record = entry["file"]
    assert record["name"] == "clip.bin"
    assert isolated_store.find_file(record["id"]) is not None, "no vault record was written"

    assert _wait_for(lambda: done), "on_done never fired"
    assert done[0]["id"] == record["id"], "on_done did not fire with the record"

def test_a_completed_upload_leaves_no_pending_row_behind(source_file, monkeypatch, isolated_store):

    _fake_transfer(monkeypatch)
    upload_id = shared.start_background_upload(source_file, "clip.bin", None, 1_900_000_000)
    assert _wait_for(lambda: shared.uploads.get(upload_id, {}).get("status") == "done")
    assert _wait_for(lambda: isolated_store.find_pending_upload(upload_id) is None), \
        "the pending row survived a successful upload"

def test_cancelling_mid_transfer_keeps_the_row_resumable(source_file, monkeypatch, isolated_store):

    started = threading.Event()
    release = threading.Event()

    def _blocking_upload(*args, **kwargs):
        started.set()
        release.wait(timeout=5)
        raise telegram_client.UploadCancelled()

    monkeypatch.setattr(telegram_client, "upload_file_parallel", _blocking_upload)
    monkeypatch.setattr(telegram_client, "upload_file", _blocking_upload)
    monkeypatch.setattr(telegram_client, "require_archive_chat", lambda: -100)

    upload_id = shared.start_background_upload(source_file, "clip.bin", None, 1_900_000_000)
    assert started.wait(timeout=5), "the upload thread never reached the transfer"
    release.set()

    assert _wait_for(lambda: shared.uploads.get(upload_id, {}).get("status") == "cancelled"), \
        shared.uploads.get(upload_id)
    assert isolated_store.find_pending_upload(upload_id) is not None, \
        "a cancelled upload lost its pending row - nothing left to resume from"
    assert os.path.exists(source_file), "the source file was deleted out from under a resume"

def test_resume_reports_prior_progress_from_its_very_first_poll(source_file, monkeypatch, isolated_store):

    _fake_transfer(monkeypatch)
    resume_chunks = [{"message_id": 1, "size_bytes": 1024}]
    upload_id = shared.start_background_upload(
        source_file, "clip.bin", None, 1_900_000_000,
        resume_chunks=resume_chunks,
        resume_part_state={"file_id": 9, "part_size": 512, "parts_sent": 2})

    entry = shared.uploads[upload_id]
    assert entry["bytes_done"] == 1024 + (512 * 2), entry
    assert entry["chunks_done"] == 1

def test_duplicate_content_is_reported_instead_of_uploaded(source_file, monkeypatch, isolated_store):

    uploaded = []
    _fake_transfer(monkeypatch, on_call=lambda kw: uploaded.append(1))

    first = shared.start_background_upload(source_file, "clip.bin", None, 1_900_000_000)
    assert _wait_for(lambda: shared.uploads.get(first, {}).get("status") == "done")
    assert _wait_until_settled(first, isolated_store)
    assert len(uploaded) == 1

    seen = []
    second = shared.start_background_upload(
        source_file, "clip.bin", None, 1_900_000_000, on_duplicate=seen.append)
    assert _wait_for(lambda: shared.uploads.get(second, {}).get("status") == "duplicate"), \
        shared.uploads.get(second)
    assert len(uploaded) == 1, "the duplicate was uploaded again anyway"
    assert seen and seen[0]["id"] == shared.uploads[first]["file"]["id"], \
        "on_duplicate did not report the existing record"

def test_force_uploads_a_known_duplicate(source_file, monkeypatch, isolated_store):

    uploaded = []
    _fake_transfer(monkeypatch, on_call=lambda kw: uploaded.append(1))
    first = shared.start_background_upload(source_file, "clip.bin", None, 1_900_000_000)
    assert _wait_for(lambda: shared.uploads.get(first, {}).get("status") == "done")
    assert _wait_until_settled(first, isolated_store)

    second = shared.start_background_upload(
        source_file, "clip.bin", None, 1_900_000_000, force=True)
    assert _wait_for(lambda: shared.uploads.get(second, {}).get("status") == "done"), \
        shared.uploads.get(second)
    assert len(uploaded) == 2
