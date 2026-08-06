import io
import os
import time

import pytest

import shared
import store
import telegram_client
from tests.conftest import isolated_store

@pytest.fixture
def client(isolated_store):
    import app as app_module
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c

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
            if not any(e.get("status") == "uploading" for e in shared.uploads.values()):
                break
        time.sleep(0.02)
    _reset()

def _wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False

def _fake_transfer(monkeypatch):
    def _upload(*args, **kwargs):
        return -100, [{"message_id": 5, "size_bytes": 9}]

    monkeypatch.setattr(telegram_client, "upload_file_parallel", _upload)
    monkeypatch.setattr(telegram_client, "upload_file", _upload)
    monkeypatch.setattr(telegram_client, "require_archive_chat", lambda: -100)

def _drop(client, name="dropped.txt", body=b"some data", folder_id=None, relative_path=None):
    data = {"file": (io.BytesIO(body), name)}
    if folder_id:
        data["folder_id"] = folder_id
    if relative_path:
        data["relative_path"] = relative_path
    return client.post("/api/uploads/queued/stage", data=data,
                       content_type="multipart/form-data")

def test_a_dropped_file_becomes_a_durable_queued_row(client, isolated_store):

    resp = _drop(client)
    assert resp.status_code == 200
    staged = resp.get_json()

    assert os.path.isfile(staged["file_path"]), "the dropped bytes were not staged to disk"
    assert store.DATA_DIR in os.path.abspath(staged["file_path"]), \
        "staged outside DATA_DIR - a restart could lose it to temp cleanup"
    row = isolated_store.find_queued_upload(staged["id"])
    assert row is not None, "nothing would resume this drop after a restart"
    assert row["owns_local_path"], "the app must own this copy, or nothing ever deletes it"

def test_the_full_drop_to_uploaded_path(client, monkeypatch, isolated_store):
    _fake_transfer(monkeypatch)
    staged = _drop(client, name="report.txt", body=b"some data").get_json()

    resp = client.post("/api/uploads/start-from-path", json={
        "file_path": staged["file_path"], "filename": "report.txt",
        "folder_id": None, "queued_id": staged["id"],
    })
    assert resp.status_code == 200, resp.get_json()
    upload_id = resp.get_json()["upload_id"]

    assert _wait_for(lambda: shared.uploads.get(upload_id, {}).get("status") == "done"), \
        shared.uploads.get(upload_id)
    record = shared.uploads[upload_id]["file"]
    assert isolated_store.find_file(record["id"])["name"] == "report.txt"

def test_the_staged_copy_is_deleted_once_it_has_been_uploaded(client, monkeypatch, isolated_store):

    _fake_transfer(monkeypatch)
    staged = _drop(client).get_json()
    path = staged["file_path"]

    resp = client.post("/api/uploads/start-from-path", json={
        "file_path": path, "filename": "dropped.txt",
        "folder_id": None, "queued_id": staged["id"],
    })
    upload_id = resp.get_json()["upload_id"]
    assert _wait_for(lambda: shared.uploads.get(upload_id, {}).get("status") == "done")
    assert _wait_for(lambda: not os.path.exists(path)), \
        "the staged copy was left behind after a successful upload"

def test_dismissing_a_queued_drop_deletes_its_staged_copy(client, isolated_store):

    staged = _drop(client).get_json()
    path = staged["file_path"]
    assert os.path.isfile(path)

    resp = client.post(f"/api/uploads/queued/{staged['id']}/dismiss")
    assert resp.status_code == 200
    assert isolated_store.find_queued_upload(staged["id"]) is None
    assert not os.path.exists(path), "dismissing a drop leaked its staged copy"

def test_relative_path_survives_the_handoff(client, monkeypatch, isolated_store):

    staged = _drop(client, name="inner.txt", relative_path="outer/inner.txt").get_json()
    assert staged["relative_path"] == "outer/inner.txt"
    row = isolated_store.find_queued_upload(staged["id"])
    assert row["relative_path"] == "outer/inner.txt"

def test_a_drop_into_a_deleted_folder_still_uploads(client, isolated_store):

    folder, _ = isolated_store.create_folder("Doomed", None)
    isolated_store.soft_delete_folder(folder["id"])

    staged = _drop(client, folder_id=folder["id"]).get_json()
    assert staged["folder_id"] is None, "expected the documented root fallback"
    assert isolated_store.find_queued_upload(staged["id"]) is not None

def test_a_failed_stage_leaves_no_orphaned_copy(client, monkeypatch, isolated_store):

    seen = {}

    def _boom(rows):
        seen["path"] = rows[0]["file_path"]
        raise RuntimeError("disk full")

    monkeypatch.setattr(store, "save_queued_uploads", _boom)
    with pytest.raises(RuntimeError):
        _drop(client)
    assert "path" in seen
    assert not os.path.exists(seen["path"]), "a failed stage leaked its temp copy"
