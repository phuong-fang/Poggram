import json
from unittest.mock import MagicMock, patch

import pytest

import app
import store
from tests.conftest import isolated_store

@pytest.fixture
def client(isolated_store):
    app.app.config["TESTING"] = True
    with app.app.test_client() as client:
        yield client

def test_list_folders_empty(client):
    resp = client.get("/api/folders")
    assert resp.status_code == 200
    assert resp.get_json() == []

def test_create_folder_route(client):
    resp = client.post("/api/folders", json={"name": "Test Folder"})
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["name"] == "Test Folder"
    assert data["id"] is not None

def test_create_folder_empty_name_route(client):
    resp = client.post("/api/folders", json={"name": ""})
    assert resp.status_code == 400

def test_list_files_empty(client):
    resp = client.get("/api/files")
    assert resp.status_code == 200
    assert resp.get_json() == []

def test_create_file_route_no_file(client):
    resp = client.post("/api/files")
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False

def test_get_upload_status_not_found(client):
    resp = client.get("/api/uploads/nonexistent")
    assert resp.status_code == 404

def test_cancel_upload_not_found(client):
    resp = client.post("/api/uploads/nonexistent/cancel")
    assert resp.status_code == 404

def test_continue_upload_not_found(client):
    resp = client.post("/api/uploads/nonexistent/continue")
    assert resp.status_code == 404

def test_telegram_status_route(client):
    with patch("app.telegram_client") as mock_tg:
        mock_tg.status.return_value = {
            "connected": False,
            "phone_number": None,
            "archive_chat_id": None,
            "archive_chat_title": None,
            "is_premium": False,
            "max_chunk_size_bytes": 1_900_000_000,
        }
        resp = client.get("/api/telegram/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "connected" in data
        assert "max_cache_bytes" in data

def test_cache_summary_empty(client):
    resp = client.get("/api/cache/summary")
    assert resp.status_code == 200
    assert resp.get_json()["bytes"] == 0

def test_cache_clear_empty(client):
    resp = client.post("/api/cache/clear")
    assert resp.status_code == 200
    assert resp.get_json()["bytes_freed"] == 0

def test_stats_empty(client):
    resp = client.get("/api/stats")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["file_count"] == 0
    assert data["total_current_bytes"] == 0

def test_trash_empty(client):
    resp = client.get("/api/trash")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["folders"] == []
    assert data["files"] == []

def test_update_max_chunk_size(client):
    resp = client.put("/api/settings/max-chunk-size", json={"max_chunk_size_bytes": 500_000_000})
    assert resp.status_code == 200

def test_update_max_chunk_size_too_small(client):
    resp = client.put("/api/settings/max-chunk-size", json={"max_chunk_size_bytes": 1000})
    assert resp.status_code == 400

def test_update_max_cache_size(client):
    resp = client.put("/api/settings/max-cache-size", json={"max_cache_bytes": 1_000_000_000})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["max_cache_bytes"] == 1_000_000_000

def test_update_max_cache_size_negative(client):
    resp = client.put("/api/settings/max-cache-size", json={"max_cache_bytes": -1})
    assert resp.status_code == 400

def test_update_parallel_transfers(client):
    resp = client.put("/api/settings/parallel-transfers", json={"max_parallel_transfers": 5})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["max_parallel_transfers"] == 5

def test_update_parallel_transfers_clamped(client):
    resp = client.put("/api/settings/parallel-transfers", json={"max_parallel_transfers": 999})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["max_parallel_transfers"] == 10

def test_upload_streams_clamped_to_sixteen(client):
    resp = client.put("/api/settings/upload", json={"upload_parallel_workers": 999, "upload_part_size_kb": 0})
    assert resp.status_code == 200
    assert resp.get_json()["upload_parallel_workers"] == 16

def test_download_streams_clamped_to_sixteen(client):
    resp = client.put("/api/settings/download", json={"download_parallel_workers": 999})
    assert resp.status_code == 200
    assert resp.get_json()["download_parallel_workers"] == 16

def test_stream_settings_accept_a_value_inside_the_range(client):
    up = client.put("/api/settings/upload", json={"upload_parallel_workers": 12, "upload_part_size_kb": 0})
    down = client.put("/api/settings/download", json={"download_parallel_workers": 12})
    assert up.get_json()["upload_parallel_workers"] == 12
    assert down.get_json()["download_parallel_workers"] == 12

def test_stream_settings_share_the_same_default(isolated_store):
    settings = isolated_store.load_settings()
    assert settings["upload_parallel_workers"] == 8
    assert settings["download_parallel_workers"] == 8

def test_index_route(client):
    resp = client.get("/")
    assert resp.status_code == 200

def test_max_content_length_is_above_any_plausible_file(client):

    configured = app.app.config["MAX_CONTENT_LENGTH"]
    assert configured is None or configured >= 32_000_000_000

def test_a_body_over_the_cap_is_still_rejected(client, monkeypatch):

    from io import BytesIO

    monkeypatch.setitem(app.app.config, "MAX_CONTENT_LENGTH", 1024)
    resp = client.post(
        "/api/files",
        data={"file": (BytesIO(b"x" * 8192), "big.bin")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 413

def test_file_list_omits_the_heavy_server_only_fields(client, isolated_store):

    folder, _ = isolated_store.create_folder("F", None)
    isolated_store.save_files([{
        "id": "f1", "name": "a.bin", "folder_id": folder["id"], "size_bytes": 5,
        "mime_type": "application/octet-stream", "telegram_chat_id": 1,
        "chunks": [{"message_id": 1, "size_bytes": 5}], "cached_chunks": [False],
        "versions": [{"chunks": [{"message_id": 1, "size_bytes": 5}], "size_bytes": 5,
                      "mime_type": None, "cached_chunks": [False],
                      "uploaded_at": "2026-08-06T00:00:00", "content_hash": "h",
                      "has_thumbnail": False}],
        "current_version": 0,
        "date_uploaded": "2026-08-06T00:00:00", "date_modified": "2026-08-06T00:00:00",
        "deleted": False,
    }])

    record = client.get("/api/files").get_json()[0]
    for omitted in ("chunks", "cached_chunks", "versions"):
        assert omitted not in record, f"{omitted} is still being shipped to the browser"

    for kept in ("id", "name", "folder_id", "size_bytes", "mime_type",
                 "date_uploaded", "date_modified", "deleted", "current_version"):
        assert kept in record, f"{kept} went missing from the list payload"

def test_trash_list_is_trimmed_the_same_way(client, isolated_store):
    folder, _ = isolated_store.create_folder("F", None)
    isolated_store.save_files([{
        "id": "f1", "name": "a.bin", "folder_id": folder["id"], "size_bytes": 5,
        "mime_type": "application/octet-stream", "telegram_chat_id": 1,
        "chunks": [{"message_id": 1, "size_bytes": 5}], "cached_chunks": [False],
        "versions": [], "current_version": 0,
        "date_uploaded": "2026-08-06T00:00:00", "date_modified": "2026-08-06T00:00:00",
        "deleted": True,
    }])
    record = client.get("/api/trash").get_json()["files"][0]
    assert "chunks" not in record and "versions" not in record
    assert record["id"] == "f1"

def test_server_side_users_of_versions_still_get_them(isolated_store):

    folder, _ = isolated_store.create_folder("F", None)
    isolated_store.save_files([{
        "id": "f1", "name": "a.bin", "folder_id": folder["id"], "size_bytes": 5,
        "mime_type": "application/octet-stream", "telegram_chat_id": 1,
        "chunks": [{"message_id": 7, "size_bytes": 5}], "cached_chunks": [False],
        "versions": [{"chunks": [{"message_id": 7, "size_bytes": 5}], "size_bytes": 5,
                      "mime_type": None, "cached_chunks": [False],
                      "uploaded_at": "2026-08-06T00:00:00", "content_hash": "h",
                      "has_thumbnail": False}],
        "current_version": 0,
        "date_uploaded": "2026-08-06T00:00:00", "date_modified": "2026-08-06T00:00:00",
        "deleted": False,
    }])
    record = isolated_store.load_files()[0]
    assert record["versions"][0]["chunks"][0]["message_id"] == 7
    assert record["chunks"] and "cached_chunks" in record
