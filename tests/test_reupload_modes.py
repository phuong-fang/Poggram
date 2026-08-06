import os
from unittest.mock import MagicMock

import pytest

import store
import sync_engine
from tests.conftest import isolated_store

@pytest.fixture
def synced_file(tmp_path, isolated_store, monkeypatch):

    local = tmp_path / "notes.txt"
    local.write_bytes(b"new content")
    st = os.stat(local)

    folder, err = isolated_store.create_folder("Synced", None)
    assert err is None, err
    folder_id = folder["id"]

    isolated_store.save_files([{
        "id": "vault-old", "name": "notes.txt", "folder_id": folder_id, "size_bytes": 3,
        "mime_type": "text/plain", "telegram_chat_id": 1, "chunks": [],
        "cached_chunks": [], "versions": [], "date_uploaded": "2026-08-01T00:00:00",
        "date_modified": "2026-08-01T00:00:00", "deleted": False,
    }])
    isolated_store.upsert_sync_record({
        "local_path": str(local), "pair_id": "pair-1", "vault_file_id": "vault-old",
        "content_hash": "old-hash", "size_bytes": 3, "mtime": st.st_mtime - 100,
        "local_inode": st.st_ino, "status": "synced",
    })
    monkeypatch.setattr(store, "find_sync_pair", lambda pid: {"id": pid, "paused": False})
    monkeypatch.setattr(sync_engine, "_get_or_create_vault_folder", lambda *a, **k: folder_id)
    monkeypatch.setattr(sync_engine, "_wait_until_stable", lambda p: True)
    return local, folder_id

def _capture_upload(monkeypatch, uploaded_record):

    seen = {}

    def _start(path, filename, folder_id, max_chunk, **kwargs):
        seen.update(kwargs)
        seen["path"] = path
        on_done = kwargs.get("on_done")
        if on_done:
            on_done(uploaded_record)
        return "upload-1"

    monkeypatch.setattr(sync_engine, "_start_upload_fn", _start, raising=False)
    return seen

def _change(local):
    st = os.stat(local)
    return {"path": str(local), "content_hash": "new-hash",
            "size_bytes": st.st_size, "mtime": st.st_mtime, "inode": st.st_ino}

def test_flag_records_the_change_and_uploads_nothing(synced_file, monkeypatch, isolated_store):
    synced_file, folder_id = synced_file
    seen = _capture_upload(monkeypatch, {"id": "vault-new"})
    sync_engine._apply_change(_change(synced_file), "pair-1",
                              {"folder_id": folder_id, "reupload_mode": "flag"},
                              root_local_path=str(synced_file.parent))
    assert "path" not in seen, "flag mode uploaded, when its whole point is not to"
    record = isolated_store.find_sync_record(str(synced_file), "pair-1")
    assert record["status"] == "changed"
    assert record["vault_file_id"] == "vault-old", "flag mode must not repoint the record"

def test_version_uploads_over_the_same_vault_file(synced_file, monkeypatch, isolated_store):
    synced_file, folder_id = synced_file
    seen = _capture_upload(monkeypatch, {"id": "vault-old", "content_hash": "new-hash"})
    sync_engine._apply_change(_change(synced_file), "pair-1",
                              {"folder_id": folder_id, "reupload_mode": "version"},
                              root_local_path=str(synced_file.parent))
    assert seen.get("target_file_id") == "vault-old", (
        "version mode must upload INTO the existing file, or it isn't versioning"
    )
    record = isolated_store.find_sync_record(str(synced_file), "pair-1")
    assert record["status"] == "synced"
    assert record["vault_file_id"] == "vault-old"
    assert record["content_hash"] == "new-hash"

def test_soft_delete_trashes_the_old_file_and_points_at_the_new_one(
        synced_file, monkeypatch, isolated_store):
    synced_file, folder_id = synced_file
    seen = _capture_upload(monkeypatch, {"id": "vault-new", "content_hash": "new-hash"})
    sync_engine._apply_change(_change(synced_file), "pair-1",
                              {"folder_id": folder_id, "reupload_mode": "soft_delete"},
                              root_local_path=str(synced_file.parent))
    assert "target_file_id" not in seen, "soft_delete uploads a NEW file, not a version"
    old = isolated_store.find_file("vault-old")
    assert old["deleted"] is True, "the superseded file was not sent to Trash"
    record = isolated_store.find_sync_record(str(synced_file), "pair-1")
    assert record["vault_file_id"] == "vault-new"
    assert record["status"] == "synced"

def test_new_file_keeps_the_old_one_visible(synced_file, monkeypatch, isolated_store):
    synced_file, folder_id = synced_file
    seen = _capture_upload(monkeypatch, {"id": "vault-new", "content_hash": "new-hash"})
    sync_engine._apply_change(_change(synced_file), "pair-1",
                              {"folder_id": folder_id, "reupload_mode": "new_file"},
                              root_local_path=str(synced_file.parent))
    assert "target_file_id" not in seen
    old = isolated_store.find_file("vault-old")
    assert old["deleted"] is False, "new_file mode must leave the previous file alone"
    record = isolated_store.find_sync_record(str(synced_file), "pair-1")
    assert record["vault_file_id"] == "vault-new"
