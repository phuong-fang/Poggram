import json
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

def test_interrupted_transfers_shows_part_level_progress(client, isolated_store, tmp_path):

    local_file = tmp_path / "video.mp4"
    local_file.write_bytes(b"x" * 1000)

    isolated_store.save_pending_upload("up1", {
        "local_path": str(local_file), "filename": "video.mp4", "folder_id": None,
        "target_file_id": None, "source": "user", "size_bytes": 1000,
        "max_chunk_size": 1_900_000_000, "telegram_chat_id": "-100123",
        "chunks": [], "skip_duplicate_check": False, "force": False,
        "relative_path": None, "owns_local_path": False,
    })
    isolated_store.update_pending_upload_part_state("up1", 999, 100, 4)

    assert "up1" not in shared.uploads

    resp = client.get("/api/transfers/interrupted")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["uploads"]) == 1
    entry = data["uploads"][0]
    assert entry["bytes_done"] == 400
    assert entry["bytes_total"] == 1000
    assert entry["resumable"] is True

def test_interrupted_transfers_not_resumable_if_file_changed(client, isolated_store, tmp_path):
    local_file = tmp_path / "video.mp4"
    local_file.write_bytes(b"x" * 1000)

    isolated_store.save_pending_upload("up1", {
        "local_path": str(local_file), "filename": "video.mp4", "folder_id": None,
        "target_file_id": None, "source": "user", "size_bytes": 999999,
        "max_chunk_size": 1_900_000_000, "telegram_chat_id": "-100123",
        "chunks": [], "skip_duplicate_check": False, "force": False,
        "relative_path": None, "owns_local_path": False,
    })

    resp = client.get("/api/transfers/interrupted")
    data = resp.get_json()
    assert data["uploads"][0]["resumable"] is False

@pytest.fixture(autouse=True)
def _reset_shared_state():
    yield
    shared.uploads.clear()
    shared.upload_retry_info.clear()
    shared.upload_cancel_tokens.clear()

def test_cancel_interrupted_upload_route_deletes_pending_row_and_orphaned_chunks(client, isolated_store, tmp_path):

    local_file = tmp_path / "video.mp4"
    local_file.write_bytes(b"x" * 1000)
    isolated_store.save_pending_upload("up1", {
        "local_path": str(local_file), "filename": "video.mp4", "folder_id": None,
        "target_file_id": None, "source": "user", "size_bytes": 1000,
        "max_chunk_size": 1_900_000_000, "telegram_chat_id": "-100123",
        "chunks": [{"message_id": 111, "size_bytes": 1000}], "skip_duplicate_check": False,
        "force": False, "relative_path": None, "owns_local_path": False,
    })

    with patch("telegram_client.delete_documents") as mock_delete:
        resp = client.post("/api/uploads/interrupted/up1/cancel")

    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}
    mock_delete.assert_called_once_with("-100123", [111])
    assert isolated_store.find_pending_upload("up1") is None

def test_cancel_interrupted_upload_route_cleans_up_live_session_dismiss(client, isolated_store, tmp_path):

    local_file = tmp_path / "video.mp4"
    local_file.write_bytes(b"x" * 1000)
    isolated_store.save_pending_upload("up1", {
        "local_path": str(local_file), "filename": "video.mp4", "folder_id": None,
        "target_file_id": None, "source": "user", "size_bytes": 1000,
        "max_chunk_size": 1_900_000_000, "telegram_chat_id": "-100123",
        "chunks": [], "skip_duplicate_check": False, "force": False,
        "relative_path": None, "owns_local_path": False,
    })
    shared.uploads["up1"] = {"status": "cancelled"}
    shared.upload_retry_info["up1"] = {"file_path": str(local_file)}
    shared.upload_cancel_tokens["up1"] = object()

    resp = client.post("/api/uploads/interrupted/up1/cancel")

    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}
    assert isolated_store.find_pending_upload("up1") is None
    assert "up1" not in shared.uploads
    assert "up1" not in shared.upload_retry_info
    assert "up1" not in shared.upload_cancel_tokens

def test_cancel_interrupted_upload_route_live_dismiss_with_no_pending_row(client, isolated_store):

    shared.uploads["up1"] = {"status": "cancelled"}
    shared.upload_retry_info["up1"] = {"file_path": "/fake/path"}

    resp = client.post("/api/uploads/interrupted/up1/cancel")

    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}
    assert "up1" not in shared.uploads
    assert "up1" not in shared.upload_retry_info

def test_cancel_interrupted_upload_route_not_found_when_nothing_exists(client, isolated_store):
    resp = client.post("/api/uploads/interrupted/nonexistent/cancel")
    assert resp.status_code == 404
