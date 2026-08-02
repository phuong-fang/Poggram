from unittest.mock import patch

import pytest

import app
import shared
import store
from tests.conftest import isolated_store

@pytest.fixture
def client(isolated_store):
    app.app.config["TESTING"] = True
    with app.app.test_client() as client:
        yield client

@pytest.fixture(autouse=True)
def _reset_shared_state():
    yield
    shared.uploads.clear()
    shared.upload_retry_info.clear()
    shared.upload_cancel_tokens.clear()

def test_continue_upload_route_passes_resume_chunks(client, isolated_store, tmp_path):
    real_file = tmp_path / "big.bin"
    real_file.write_bytes(b"x" * 1000)

    upload_id = "up1"
    shared.uploads[upload_id] = {"status": "cancelled"}
    shared.upload_retry_info[upload_id] = {
        "file_path": str(real_file), "filename": "big.bin", "folder_id": None,
        "max_chunk_size": 500, "cleanup_path": None, "target_file_id": None,
        "skip_duplicate_check": False, "force": False, "size_bytes": 1000,
        "resume_chunks": [{"message_id": 1, "size_bytes": 500}],
        "resume_part_state": {"file_id": "222", "part_size": 100, "parts_sent": 1},
    }

    with patch("shared.start_background_upload", return_value="new_id") as mock_start:
        resp = client.post(f"/api/uploads/{upload_id}/continue")

    assert resp.status_code == 202
    assert resp.get_json()["upload_id"] == "new_id"
    _, kwargs = mock_start.call_args

    assert kwargs["resume_chunks"] == [{"message_id": 1, "size_bytes": 500}]

    assert kwargs["resume_part_state"] == {"file_id": "222", "part_size": 100, "parts_sent": 1}

    assert upload_id not in shared.uploads

def test_continue_upload_route_falls_back_to_stale_size_never_resumes_changed_file(client, isolated_store, tmp_path):
    real_file = tmp_path / "big.bin"
    real_file.write_bytes(b"x" * 999)

    upload_id = "up1"
    shared.uploads[upload_id] = {"status": "cancelled"}
    shared.upload_retry_info[upload_id] = {
        "file_path": str(real_file), "filename": "big.bin", "folder_id": None,
        "max_chunk_size": 500, "cleanup_path": None, "target_file_id": None,
        "skip_duplicate_check": False, "force": False, "size_bytes": 1000,
        "resume_chunks": [{"message_id": 1, "size_bytes": 500}],
        "resume_part_state": {"file_id": "222", "part_size": 100, "parts_sent": 1},
    }

    with patch("shared.start_background_upload", return_value="new_id") as mock_start:
        client.post(f"/api/uploads/{upload_id}/continue")

    _, kwargs = mock_start.call_args
    assert kwargs["resume_chunks"] is None
    assert kwargs["resume_part_state"] is None

def test_continue_does_not_regress_to_zero_when_resumed_attempt_cancelled_before_persisting(
    client, isolated_store, tmp_path,
):

    real_file = tmp_path / "big.bin"
    real_file.write_bytes(b"x" * 1000)

    first_upload_id = "up1"
    shared.uploads[first_upload_id] = {"status": "cancelled"}
    shared.upload_retry_info[first_upload_id] = {
        "file_path": str(real_file), "filename": "big.bin", "folder_id": None,
        "max_chunk_size": 500, "cleanup_path": None, "target_file_id": None,
        "skip_duplicate_check": False, "force": False, "size_bytes": 1000,
        "resume_chunks": [{"message_id": 1, "size_bytes": 500}],
        "resume_part_state": {"file_id": "222", "part_size": 100, "parts_sent": 1},
    }

    def fake_start_background_upload(*args, **kwargs):

        new_id = "up2"
        shared.uploads[new_id] = {"status": "cancelled"}
        shared.upload_retry_info[new_id] = {
            "file_path": kwargs.get("file_path", args[0] if args else str(real_file)),
            "filename": "big.bin", "folder_id": None, "max_chunk_size": 500,
            "cleanup_path": kwargs.get("cleanup_path"), "target_file_id": kwargs.get("target_file_id"),
            "skip_duplicate_check": kwargs.get("skip_duplicate_check", False),
            "force": kwargs.get("force", False), "size_bytes": 1000,
            "resume_chunks": kwargs.get("resume_chunks") or [],
            "resume_part_state": kwargs.get("resume_part_state"),
        }
        return new_id

    with patch("shared.start_background_upload", side_effect=fake_start_background_upload):
        resp1 = client.post(f"/api/uploads/{first_upload_id}/continue")
    assert resp1.get_json()["upload_id"] == "up2"

    with patch("shared.start_background_upload", return_value="up3") as mock_start:
        resp2 = client.post("/api/uploads/up2/continue")
    assert resp2.get_json()["upload_id"] == "up3"
    _, kwargs = mock_start.call_args
    assert kwargs["resume_chunks"] == [{"message_id": 1, "size_bytes": 500}]
    assert kwargs["resume_part_state"] == {"file_id": "222", "part_size": 100, "parts_sent": 1}

def test_get_status_does_not_pop_cancelled_and_continue_still_works(client, isolated_store, tmp_path):

    real_file = tmp_path / "big.bin"
    real_file.write_bytes(b"x" * 1000)

    upload_id = "up1"
    shared.uploads[upload_id] = {
        "status": "cancelled", "chunks_done": 0, "chunks_total": 1,
        "bytes_done": 500, "bytes_total": 1000, "file": None, "error": None,
        "source": "user", "filename": "big.bin", "relative_path": None, "folder_id": None,
    }
    shared.upload_retry_info[upload_id] = {
        "file_path": str(real_file), "filename": "big.bin", "folder_id": None,
        "max_chunk_size": 1_900_000_000, "cleanup_path": None, "target_file_id": None,
        "skip_duplicate_check": False, "force": False,
    }

    status_resp = client.get(f"/api/uploads/{upload_id}")
    assert status_resp.status_code == 200
    assert status_resp.get_json()["status"] == "cancelled"

    assert upload_id in shared.uploads

    with patch("shared.start_background_upload", return_value="new_id"):
        continue_resp = client.post(f"/api/uploads/{upload_id}/continue")
    assert continue_resp.status_code == 202
    assert continue_resp.get_json()["upload_id"] == "new_id"
