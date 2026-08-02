import time
from unittest.mock import patch

import pytest

import shared
import telegram_client
from tests.conftest import isolated_store

def _wait_for_status(upload_id, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        with shared.uploads_lock:
            status = shared.uploads.get(upload_id, {}).get("status")
        if status not in ("uploading", "queued", None):
            return status
        time.sleep(0.01)
    raise AssertionError(f"upload {upload_id} never reached a terminal status")

@pytest.fixture(autouse=True)
def _reset_shared_state():
    yield
    shared.uploads.clear()
    shared.upload_retry_info.clear()
    shared.upload_cancel_tokens.clear()

def test_resume_chunks_reflected_in_initial_status(isolated_store, tmp_path):
    real_file = tmp_path / "big.bin"
    real_file.write_bytes(b"x" * 3000)

    resume_chunks = [
        {"message_id": 1, "size_bytes": 1000},
        {"message_id": 2, "size_bytes": 1000},
    ]

    with patch("telegram_client.compute_content_hash", return_value="hashA"), \
         patch("telegram_client.require_archive_chat", return_value="-100999"), \
         patch("telegram_client.upload_file_parallel", side_effect=telegram_client.UploadCancelled()), \
         patch("store.find_duplicate_by_hash", return_value=None):
        upload_id = shared.start_background_upload(
            str(real_file), "big.bin", None, 1000, resume_chunks=resume_chunks,
        )

        with shared.uploads_lock:
            info = dict(shared.uploads[upload_id])
        _wait_for_status(upload_id)

    assert info["bytes_done"] == 2000
    assert info["chunks_done"] == 2

def test_resume_part_state_reflected_in_initial_status(isolated_store, tmp_path):
    real_file = tmp_path / "big.bin"
    real_file.write_bytes(b"x" * 3000)

    resume_chunks = [{"message_id": 1, "size_bytes": 1000}]
    resume_part_state = {"file_id": 999, "part_size": 100, "parts_sent": 4}

    with patch("telegram_client.compute_content_hash", return_value="hashB"), \
         patch("telegram_client.require_archive_chat", return_value="-100999"), \
         patch("telegram_client.upload_file_parallel", side_effect=telegram_client.UploadCancelled()), \
         patch("store.find_duplicate_by_hash", return_value=None):
        upload_id = shared.start_background_upload(
            str(real_file), "big.bin", None, 1000,
            resume_chunks=resume_chunks, resume_part_state=resume_part_state,
        )
        with shared.uploads_lock:
            info = dict(shared.uploads[upload_id])
        _wait_for_status(upload_id)

    assert info["bytes_done"] == 1400
    assert info["chunks_done"] == 1

def test_fresh_upload_still_starts_at_zero(isolated_store, tmp_path):
    real_file = tmp_path / "small.bin"
    real_file.write_bytes(b"x" * 100)

    with patch("telegram_client.compute_content_hash", return_value="hashC"), \
         patch("telegram_client.require_archive_chat", return_value="-100999"), \
         patch("telegram_client.upload_file_parallel", side_effect=telegram_client.UploadCancelled()), \
         patch("store.find_duplicate_by_hash", return_value=None):
        upload_id = shared.start_background_upload(str(real_file), "small.bin", None, 1000)
        with shared.uploads_lock:
            info = dict(shared.uploads[upload_id])
        _wait_for_status(upload_id)

    assert info["bytes_done"] == 0
    assert info["chunks_done"] == 0
