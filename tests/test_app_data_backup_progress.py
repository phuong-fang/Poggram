import time
from unittest.mock import patch

import pytest

import app
import shared
from tests.conftest import isolated_store

@pytest.fixture
def client(isolated_store):
    app.app.config["TESTING"] = True
    with app.app.test_client() as client:
        yield client

@pytest.fixture(autouse=True)
def _reset_backup_status():
    with shared.backup_status_lock:
        shared.backup_status.clear()
        shared.backup_status.update({"status": "idle"})
    yield

def _wait_for(predicate, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False

def test_run_backup_reports_each_stage_then_done(isolated_store):
    seen = []

    def fake_snapshot(on_build_progress=None, on_upload_progress=None, on_stage=None):
        on_stage("building")
        on_build_progress(5, 10)
        seen.append(dict(shared.backup_status))
        on_stage("uploading")
        on_upload_progress(2048, 4096)
        seen.append(dict(shared.backup_status))
        on_stage("pruning")
        seen.append(dict(shared.backup_status))

    with patch.object(shared, "_build_and_upload_app_data_snapshot", side_effect=fake_snapshot):
        shared.run_app_data_backup()
        assert _wait_for(lambda: shared.backup_status["status"] == "done")

    assert [s["status"] for s in seen] == ["building", "uploading", "pruning"]
    assert (seen[0]["files_done"], seen[0]["files_total"]) == (5, 10)
    assert (seen[1]["bytes_done"], seen[1]["bytes_total"]) == (2048, 4096)

def test_run_backup_records_an_error_instead_of_raising(isolated_store):
    with patch.object(shared, "_build_and_upload_app_data_snapshot", side_effect=RuntimeError("no connection")):
        shared.run_app_data_backup()
        assert _wait_for(lambda: shared.backup_status["status"] == "error")

    assert shared.backup_status["error"] == "no connection"

def test_on_finished_runs_even_when_the_backup_fails(isolated_store):

    finished = []
    with patch.object(shared, "_build_and_upload_app_data_snapshot", side_effect=RuntimeError("boom")):
        shared.run_app_data_backup(on_finished=lambda: finished.append(True))
        assert _wait_for(lambda: finished)

def test_snapshot_route_returns_immediately_without_doing_the_work(client, isolated_store):

    def run_and_finish(on_finished=None):
        if on_finished:
            on_finished()

    with patch.object(shared, "run_app_data_backup", side_effect=run_and_finish) as run:
        resp = client.post("/api/app-data-backup/snapshot")

    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True, "started": True}
    run.assert_called_once()

def test_a_failure_to_start_releases_the_lock(client, isolated_store):

    with patch.object(shared, "run_app_data_backup", side_effect=RuntimeError("thread failed")):
        first = client.post("/api/app-data-backup/snapshot")
    assert first.status_code == 400

    def run_and_finish(on_finished=None):
        if on_finished:
            on_finished()

    with patch.object(shared, "run_app_data_backup", side_effect=run_and_finish):
        second = client.post("/api/app-data-backup/snapshot")
    assert second.status_code == 200, "lock was not released after the failed start"

def test_a_second_concurrent_backup_is_rejected(client, isolated_store):

    release = {}

    def capture(on_finished=None):
        release["fn"] = on_finished

    with patch.object(shared, "run_app_data_backup", side_effect=capture):
        first = client.post("/api/app-data-backup/snapshot")
        second = client.post("/api/app-data-backup/snapshot")

        assert first.status_code == 200
        assert second.status_code == 409
        assert "already in progress" in second.get_json()["error"]

        release["fn"]()
        third = client.post("/api/app-data-backup/snapshot")
        assert third.status_code == 200
        release["fn"]()

def test_backup_status_route_exposes_the_live_status(client, isolated_store):
    with shared.backup_status_lock:
        shared.backup_status.clear()
        shared.backup_status.update({"status": "uploading", "bytes_done": 10, "bytes_total": 100})

    resp = client.get("/api/app-data-backup/backup-status")

    assert resp.status_code == 200
    assert resp.get_json() == {"status": "uploading", "bytes_done": 10, "bytes_total": 100}

def test_build_snapshot_reports_thumbnail_progress(isolated_store, monkeypatch):
    import os

    os.makedirs(isolated_store.CACHE_DIR, exist_ok=True)
    for i in range(3):
        with open(os.path.join(isolated_store.CACHE_DIR, f"file{i}_v0_thumb.jpg"), "wb") as f:
            f.write(b"x")

    calls = []
    isolated_store.build_app_data_snapshot(on_progress=lambda done, total: calls.append((done, total)))

    assert calls, "expected at least one progress callback"

    assert calls[-1] == (3, 3)

def test_build_snapshot_still_works_without_a_callback(isolated_store):

    assert isinstance(isolated_store.build_app_data_snapshot(), bytes)

def _seed_thumbnails(isolated_store, n=3):
    import os
    os.makedirs(isolated_store.CACHE_DIR, exist_ok=True)
    for i in range(n):
        with open(os.path.join(isolated_store.CACHE_DIR, f"file{i}_v0_thumb.jpg"), "wb") as f:
            f.write(b"thumbnail-bytes" * 100)

def _snapshot_members(snapshot_bytes):
    import io
    import tarfile
    with tarfile.open(fileobj=io.BytesIO(snapshot_bytes), mode="r:xz") as tf:
        return tf.getnames()

def test_snapshot_excludes_thumbnails_when_asked(isolated_store):
    _seed_thumbnails(isolated_store)

    names = _snapshot_members(isolated_store.build_app_data_snapshot(include_thumbnails=False))

    assert "folders.json" in names and "files.json" in names
    assert not [n for n in names if n.startswith("cache/")], "thumbnails must be excluded"

def test_snapshot_includes_thumbnails_when_asked(isolated_store):
    _seed_thumbnails(isolated_store)

    names = _snapshot_members(isolated_store.build_app_data_snapshot(include_thumbnails=True))

    assert len([n for n in names if n.startswith("cache/")]) == 3

def test_excluding_thumbnails_makes_the_snapshot_smaller(isolated_store):
    _seed_thumbnails(isolated_store, n=20)

    with_thumbs = isolated_store.build_app_data_snapshot(include_thumbnails=True)
    without = isolated_store.build_app_data_snapshot(include_thumbnails=False)

    assert len(without) < len(with_thumbs)

def test_the_setting_drives_the_snapshot(isolated_store):

    _seed_thumbnails(isolated_store)
    isolated_store.save_settings_fields({"app_data_backup_include_thumbnails": False})

    captured = {}

    def _capture(snapshot_bytes, filename, on_progress=None):
        captured["names"] = _snapshot_members(snapshot_bytes)
        return 123

    with patch("telegram_client.upload_app_data_snapshot", side_effect=_capture), \
         patch("telegram_client.list_app_data_snapshots", return_value=[]), \
         patch("telegram_client.delete_app_data_snapshots"):
        shared._build_and_upload_app_data_snapshot()

    assert not [n for n in captured["names"] if n.startswith("cache/")]

def test_the_setting_can_turn_thumbnails_back_on(isolated_store):
    _seed_thumbnails(isolated_store)
    isolated_store.save_settings_fields({"app_data_backup_include_thumbnails": True})

    captured = {}

    def _capture(snapshot_bytes, filename, on_progress=None):
        captured["names"] = _snapshot_members(snapshot_bytes)
        return 123

    with patch("telegram_client.upload_app_data_snapshot", side_effect=_capture), \
         patch("telegram_client.list_app_data_snapshots", return_value=[]), \
         patch("telegram_client.delete_app_data_snapshots"):
        shared._build_and_upload_app_data_snapshot()

    assert len([n for n in captured["names"] if n.startswith("cache/")]) == 3

def test_default_is_to_exclude_thumbnails(isolated_store):
    assert isolated_store.load_settings()["app_data_backup_include_thumbnails"] is False

def test_restoring_a_thumbnail_less_snapshot_keeps_existing_thumbnails(isolated_store):

    import os
    _seed_thumbnails(isolated_store, n=4)
    snapshot = isolated_store.build_app_data_snapshot(include_thumbnails=False)
    before = sorted(os.listdir(isolated_store.CACHE_DIR))

    isolated_store.restore_app_data_snapshot(snapshot)

    assert sorted(os.listdir(isolated_store.CACHE_DIR)) == before
