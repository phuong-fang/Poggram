import threading
import time

import pytest

import shared
import store
from tests.conftest import isolated_store

def _drain_upload(upload_id, timeout=5.0):

    if not upload_id:
        return
    deadline = time.time() + timeout
    while time.time() < deadline:
        with shared.uploads_lock:
            info = shared.uploads.get(upload_id)
        if info is None or info.get("status") in ("done", "error", "cancelled", "duplicate"):
            time.sleep(0.15)
            return
        time.sleep(0.05)

@pytest.fixture
def queued_row(isolated_store, tmp_path):

    source = tmp_path / "example.bin"
    source.write_bytes(b"x" * 32)
    record = {
        "id": "queued-1",
        "file_path": str(source),
        "filename": "example.bin",
        "folder_id": None,
        "relative_path": None,
    }
    store.save_queued_uploads([record])
    assert [u["id"] for u in store.list_queued_uploads()] == ["queued-1"]
    return record

def test_queued_row_survives_the_wait_for_a_transfer_slot(queued_row, monkeypatch):

    monkeypatch.setattr(shared.telegram_client, "require_archive_chat", lambda: -100123, raising=False)
    monkeypatch.setattr(
        shared.telegram_client, "upload_file_parallel",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("not reached")), raising=False,
    )

    shared.upload_transfer_slot.acquire()
    upload_id = None
    try:
        upload_id = shared.start_background_upload(
            queued_row["file_path"], queued_row["filename"], None, 100,
            queued_id=queued_row["id"],
        )

        threading.Event().wait(1.2)

        queued = [u["id"] for u in store.list_queued_uploads()]
        pending = [p["id"] for p in store.list_pending_uploads()]
        assert queued or pending, (
            "upload is in NEITHER queued_uploads nor pending_uploads while it "
            "waits for a slot - restarting here loses it with no way to resume"
        )
        assert queued == ["queued-1"], "the queued row is the only record at this stage"
        assert not pending, "sanity: persistence genuinely hasn't happened yet"
    finally:
        shared.upload_transfer_slot.release()

        _drain_upload(upload_id)

def test_queued_row_is_cleared_once_the_pending_row_exists(queued_row, monkeypatch):

    persisted = threading.Event()

    def _blocking_transfer(*args, **kwargs):
        persisted.set()
        threading.Event().wait(2)
        raise RuntimeError("stop - the handoff is what's under test")

    monkeypatch.setattr(shared.telegram_client, "require_archive_chat", lambda: -100123, raising=False)
    monkeypatch.setattr(shared.telegram_client, "upload_file_parallel", _blocking_transfer, raising=False)

    shared.start_background_upload(
        queued_row["file_path"], queued_row["filename"], None, 100,
        queued_id=queued_row["id"],
    )
    assert persisted.wait(timeout=5), "upload never reached the transfer"

    assert [p["id"] for p in store.list_pending_uploads()], "pending row should exist now"
    assert store.list_queued_uploads() == [], "queued placeholder should be gone once replaced"

def test_start_from_path_checks_for_duplicates_by_default(monkeypatch, queued_row):

    captured = {}
    monkeypatch.setattr(shared, "start_background_upload", lambda *a, **k: captured.update(k) or "upload-1")

    import app as app_module

    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as client:
        response = client.post("/api/uploads/start-from-path", json={
            "file_path": queued_row["file_path"],
            "filename": queued_row["filename"],
        })

    assert response.status_code == 200, response.data
    assert captured.get("skip_duplicate_check") is False

    captured.clear()
    with app_module.app.test_client() as client:
        client.post("/api/uploads/start-from-path", json={
            "file_path": queued_row["file_path"],
            "filename": queued_row["filename"],
            "skip_duplicate_check": True,
        })
    assert captured.get("skip_duplicate_check") is True

def test_start_from_path_route_does_not_clear_the_row_itself(monkeypatch, queued_row):

    captured = {}

    def _fake_start(*args, **kwargs):
        captured.update(kwargs)
        return "upload-1"

    monkeypatch.setattr(shared, "start_background_upload", _fake_start)

    import app as app_module

    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as client:
        response = client.post("/api/uploads/start-from-path", json={
            "file_path": queued_row["file_path"],
            "filename": queued_row["filename"],
            "queued_id": queued_row["id"],
        })

    assert response.status_code == 200, response.data
    assert captured.get("queued_id") == "queued-1", (
        "route must pass queued_id to the upload instead of deleting the row"
    )
    assert [u["id"] for u in store.list_queued_uploads()] == ["queued-1"], (
        "route deleted the queued row before the pending row existed"
    )
