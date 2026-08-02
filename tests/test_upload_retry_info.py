import threading
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

def _wait_until(predicate, timeout=2.0, what="condition"):

    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError(f"timed out waiting for {what}")

@pytest.fixture(autouse=True)
def _reset_shared_state(isolated_store):

    before = set(threading.enumerate())
    yield
    for t in threading.enumerate():
        if t not in before and t is not threading.current_thread() and t.is_alive():
            t.join(timeout=2.0)
    shared.uploads.clear()
    shared.upload_retry_info.clear()
    shared.upload_cancel_tokens.clear()

def test_cleanup_path_upload_survives_cancel(isolated_store, tmp_path):
    temp_file = tmp_path / "tgv_upload_abc123"
    temp_file.write_bytes(b"x" * 1000)

    with patch("telegram_client.compute_content_hash", return_value="hash1"), \
         patch("telegram_client.require_archive_chat", return_value="-100999"), \
         patch("telegram_client.upload_file_parallel", side_effect=telegram_client.UploadCancelled()), \
         patch("store.find_duplicate_by_hash", return_value=None):
        upload_id = shared.start_background_upload(
            str(temp_file), "video.mp4", None, 1_900_000_000, cleanup_path=str(temp_file),
        )

        assert upload_id in shared.upload_retry_info
        assert shared.upload_retry_info[upload_id]["cleanup_path"] == str(temp_file)

        status = _wait_for_status(upload_id)
        assert status == "cancelled"

    assert temp_file.exists()

    record = isolated_store.find_pending_upload(upload_id)
    assert record is not None
    assert record["local_path"] == str(temp_file)

def test_native_drop_upload_still_survives_cancel(isolated_store, tmp_path):

    real_file = tmp_path / "video.mp4"
    real_file.write_bytes(b"x" * 1000)

    with patch("telegram_client.compute_content_hash", return_value="hash2"), \
         patch("telegram_client.require_archive_chat", return_value="-100999"), \
         patch("telegram_client.upload_file_parallel", side_effect=telegram_client.UploadCancelled()), \
         patch("store.find_duplicate_by_hash", return_value=None):
        upload_id = shared.start_background_upload(
            str(real_file), "video.mp4", None, 1_900_000_000, cleanup_path=None,
        )
        status = _wait_for_status(upload_id)
        assert status == "cancelled"

    assert real_file.exists()
    record = isolated_store.find_pending_upload(upload_id)
    assert record is not None

def test_on_chunk_done_clears_stale_part_state(isolated_store, tmp_path):

    real_file = tmp_path / "big.bin"
    real_file.write_bytes(b"x" * 1000)

    def fake_upload_file_parallel(*args, **kwargs):
        on_chunk_done = kwargs["on_chunk_done"]
        on_part_done = kwargs["on_part_done"]

        on_part_done(111, 100, 3)
        on_chunk_done([{"message_id": 1, "size_bytes": 500}])

        on_part_done(222, 100, 1)
        raise telegram_client.UploadCancelled()

    with patch("telegram_client.compute_content_hash", return_value="hash4"), \
         patch("telegram_client.require_archive_chat", return_value="-100999"), \
         patch("telegram_client.upload_file_parallel", side_effect=fake_upload_file_parallel), \
         patch("store.find_duplicate_by_hash", return_value=None):
        upload_id = shared.start_background_upload(
            str(real_file), "big.bin", None, 500, cleanup_path=None,
        )
        status = _wait_for_status(upload_id)
        assert status == "cancelled"

    record = isolated_store.find_pending_upload(upload_id)
    assert record is not None

    assert record["chunks"] == [{"message_id": 1, "size_bytes": 500}]

    assert record["upload_file_id"] == "222"
    assert record["upload_parts_sent"] == 1

def test_cleanup_path_upload_deleted_on_success(isolated_store, tmp_path):

    temp_file = tmp_path / "tgv_upload_done"
    temp_file.write_bytes(b"x" * 1000)

    with patch("telegram_client.compute_content_hash", return_value="hash3"), \
         patch("telegram_client.require_archive_chat", return_value="-100999"), \
         patch("telegram_client.upload_file_parallel", return_value=("-100999", [{"message_id": 1, "size_bytes": 1000}])), \
         patch("store.find_duplicate_by_hash", return_value=None), \
         patch("store.create_file", return_value={"id": "f1", "name": "video.mp4"}):
        upload_id = shared.start_background_upload(
            str(temp_file), "video.mp4", None, 1_900_000_000, cleanup_path=str(temp_file),
        )
        status = _wait_for_status(upload_id)
        assert status == "done"

    _wait_until(lambda: not temp_file.exists(), what="the temp file to be deleted")
    assert not temp_file.exists()
    assert isolated_store.find_pending_upload(upload_id) is None

def test_successful_upload_cleans_up_even_if_its_entry_is_popped_mid_flight(isolated_store, tmp_path):

    temp_file = tmp_path / "tgv_upload_popped"
    temp_file.write_bytes(b"x" * 1000)

    def _pop_as_soon_as_done(upload_id):
        deadline = time.time() + 2.0
        while time.time() < deadline:
            with shared.uploads_lock:
                info = shared.uploads.get(upload_id)
                if info and info.get("status") == "done":
                    shared.uploads.pop(upload_id, None)
                    return
            time.sleep(0.001)

    with patch("telegram_client.compute_content_hash", return_value="hashpop"), \
         patch("telegram_client.require_archive_chat", return_value="-100999"), \
         patch("telegram_client.upload_file_parallel", return_value=("-100999", [{"message_id": 1, "size_bytes": 1000}])), \
         patch("store.find_duplicate_by_hash", return_value=None), \
         patch("store.create_file", return_value={"id": "f2", "name": "popped.mp4"}):
        upload_id = shared.start_background_upload(
            str(temp_file), "popped.mp4", None, 1_900_000_000, cleanup_path=str(temp_file),
        )
        popper = threading.Thread(target=_pop_as_soon_as_done, args=(upload_id,))
        popper.start()
        popper.join()

        _wait_until(lambda: not temp_file.exists(), what="the temp file to be deleted despite the popped entry")

    assert not temp_file.exists(), "successful upload leaked its temp file when its entry was popped"
    assert isolated_store.find_pending_upload(upload_id) is None

def test_a_failing_completed_row_does_not_turn_a_successful_upload_into_an_error(isolated_store, tmp_path):

    temp_file = tmp_path / "tgv_upload_persistfail"
    temp_file.write_bytes(b"x" * 1000)
    isolated_store.save_settings_fields({"completed_uploads_persistence": "keep"})

    with patch("telegram_client.compute_content_hash", return_value="hashfail"), \
         patch("telegram_client.require_archive_chat", return_value="-100999"), \
         patch("telegram_client.upload_file_parallel", return_value=("-100999", [{"message_id": 1, "size_bytes": 1000}])), \
         patch("store.find_duplicate_by_hash", return_value=None), \
         patch("store.create_file", return_value={"id": "f3", "name": "keepfail.mp4"}), \
         patch("store.save_completed_upload", side_effect=RuntimeError("db is locked")):
        upload_id = shared.start_background_upload(
            str(temp_file), "keepfail.mp4", None, 1_900_000_000, cleanup_path=str(temp_file),
        )
        status = _wait_for_status(upload_id)

    assert status == "done", "a failed completed-row write must not mask a successful upload"
