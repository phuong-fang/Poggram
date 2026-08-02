import time
from unittest.mock import patch

import pytest

import shared
import telegram_client
from tests.conftest import isolated_store

def _wait_for_status(upload_id, timeout=2.0):
    deadline = time.time() + timeout
    saw_entry = False
    while time.time() < deadline:
        with shared.uploads_lock:
            info = shared.uploads.get(upload_id)
        if info is not None:
            saw_entry = True
            if info["status"] not in ("uploading", "queued"):
                return info["status"]
        elif saw_entry:

            return "cancelled"
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
def _reset_shared_state():
    yield
    shared.uploads.clear()
    shared.upload_retry_info.clear()
    shared.upload_cancel_tokens.clear()

def test_forget_cancel_deletes_pending_row_and_temp_file(isolated_store, tmp_path):
    temp_file = tmp_path / "tgv_upload_forget1"
    temp_file.write_bytes(b"x" * 1000)

    def fake_upload_file_parallel(*args, **kwargs):

        kwargs["cancel_token"].cancel(forget=True)
        raise telegram_client.UploadCancelled()

    with patch("telegram_client.compute_content_hash", return_value="hashF1"), \
         patch("telegram_client.require_archive_chat", return_value="-100999"), \
         patch("telegram_client.upload_file_parallel", side_effect=fake_upload_file_parallel), \
         patch("store.find_duplicate_by_hash", return_value=None):
        upload_id = shared.start_background_upload(
            str(temp_file), "video.mp4", None, 1_900_000_000, cleanup_path=str(temp_file),
        )
        status = _wait_for_status(upload_id)
        assert status == "cancelled"

    _wait_until(lambda: not temp_file.exists(), what="the temp file to be deleted")
    assert not temp_file.exists()
    _wait_until(lambda: isolated_store.find_pending_upload(upload_id) is None,
                what="the pending_uploads row to be deleted")
    assert isolated_store.find_pending_upload(upload_id) is None

    assert upload_id not in shared.upload_retry_info

def test_forget_cancel_deletes_already_sent_chunks(isolated_store, tmp_path):
    real_file = tmp_path / "big.bin"
    real_file.write_bytes(b"x" * 1000)

    def fake_upload_file_parallel(*args, **kwargs):

        kwargs["on_chunk_done"]([{"message_id": 111, "size_bytes": 500}])

        kwargs["cancel_token"].cancel(forget=True)
        raise telegram_client.UploadCancelled()

    with patch("telegram_client.compute_content_hash", return_value="hashF2"), \
         patch("telegram_client.require_archive_chat", return_value="-100999"), \
         patch("telegram_client.upload_file_parallel", side_effect=fake_upload_file_parallel), \
         patch("store.find_duplicate_by_hash", return_value=None), \
         patch("telegram_client.delete_documents") as mock_delete:
        upload_id = shared.start_background_upload(
            str(real_file), "big.bin", None, 500, cleanup_path=None,
        )
        status = _wait_for_status(upload_id)
        assert status == "cancelled"

    mock_delete.assert_called_once_with("-100999", [111])
    assert isolated_store.find_pending_upload(upload_id) is None

def test_plain_pause_cancel_is_unaffected_by_forget_logic(isolated_store, tmp_path):

    real_file = tmp_path / "video.mp4"
    real_file.write_bytes(b"x" * 1000)

    with patch("telegram_client.compute_content_hash", return_value="hashF3"), \
         patch("telegram_client.require_archive_chat", return_value="-100999"), \
         patch("telegram_client.upload_file_parallel", side_effect=telegram_client.UploadCancelled()), \
         patch("store.find_duplicate_by_hash", return_value=None):
        upload_id = shared.start_background_upload(
            str(real_file), "video.mp4", None, 1_900_000_000, cleanup_path=None,
        )
        status = _wait_for_status(upload_id)
        assert status == "cancelled"

    assert real_file.exists()
    assert isolated_store.find_pending_upload(upload_id) is not None
    assert upload_id in shared.upload_retry_info
