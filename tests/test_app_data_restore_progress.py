import os
import time
from unittest.mock import patch

import pytest

import app
import shared
import store
from tests.conftest import isolated_store

def _make_thumb(isolated_store, file_id, version_index, ext, content):
    path = isolated_store.thumbnail_path_for_ext(file_id, version_index, ext)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)
    return path

@pytest.fixture
def client(isolated_store):
    app.app.config["TESTING"] = True
    with app.app.test_client() as client:
        yield client

def _wait_for_restore_status(target_statuses, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        with shared.restore_status_lock:
            status = shared.restore_status.get("status")
        if status in target_statuses:
            return status
        time.sleep(0.01)
    raise AssertionError(f"restore_status never reached {target_statuses}, last saw {status!r}")

def test_restore_app_data_snapshot_reports_thumbnail_progress(isolated_store):
    n = 25
    for i in range(n):
        _make_thumb(isolated_store, f"{i:08x}", 0, "jpg", f"content {i}".encode() * 20)
    snapshot_bytes = isolated_store.build_app_data_snapshot()

    for name in os.listdir(store.CACHE_DIR):
        os.remove(os.path.join(store.CACHE_DIR, name))

    calls = []
    isolated_store.restore_app_data_snapshot(snapshot_bytes, on_progress=lambda done, total: calls.append((done, total)))

    assert calls

    assert calls[-1] == (n, n)
    for done, total in calls:
        assert total == n
        assert 1 <= done <= n

def test_run_app_data_restore_updates_status_through_stages_and_calls_on_finished(isolated_store, tmp_path):
    _make_thumb(isolated_store, "abc12345", 0, "jpg", b"fake jpeg bytes")
    snapshot_bytes = isolated_store.build_app_data_snapshot()

    on_finished_calls = []

    with patch("telegram_client.download_app_data_snapshot", return_value=snapshot_bytes) as mock_download:
        shared.run_app_data_restore(999, on_finished=lambda: on_finished_calls.append(True))
        status = _wait_for_restore_status(("done", "error"))

    assert status == "done"

    deadline = time.time() + 2.0
    while not on_finished_calls and time.time() < deadline:
        time.sleep(0.01)
    assert on_finished_calls == [True]
    mock_download.assert_called_once()

    assert "on_progress" in mock_download.call_args.kwargs
    with shared.restore_status_lock:
        assert shared.restore_status["error"] is None

def test_run_app_data_restore_reports_error_status_and_still_calls_on_finished(isolated_store):
    on_finished_calls = []

    with patch("telegram_client.download_app_data_snapshot", side_effect=ValueError("snapshot gone")):
        shared.run_app_data_restore(999, on_finished=lambda: on_finished_calls.append(True))
        status = _wait_for_restore_status(("done", "error"))

    assert status == "error"
    assert on_finished_calls == [True]
    with shared.restore_status_lock:
        assert "snapshot gone" in shared.restore_status["error"]

def test_restore_route_starts_in_background_and_status_route_reflects_it(client, isolated_store):
    _make_thumb(isolated_store, "abc12345", 0, "jpg", b"fake jpeg bytes")
    snapshot_bytes = isolated_store.build_app_data_snapshot()

    with patch("telegram_client.download_app_data_snapshot", return_value=snapshot_bytes):
        resp = client.post("/api/app-data-backup/snapshots/999/restore")
        assert resp.status_code == 200
        assert resp.get_json() == {"ok": True, "started": True}

        status = _wait_for_restore_status(("done", "error"))
        assert status == "done"

        status_resp = client.get("/api/app-data-backup/restore-status")
        assert status_resp.status_code == 200
        assert status_resp.get_json()["status"] == "done"

def test_restore_route_rejects_concurrent_restore(client, isolated_store):
    _make_thumb(isolated_store, "abc12345", 0, "jpg", b"fake jpeg bytes")
    snapshot_bytes = isolated_store.build_app_data_snapshot()

    release = []

    def _slow_download(*args, **kwargs):
        while not release:
            time.sleep(0.01)
        return snapshot_bytes

    with patch("telegram_client.download_app_data_snapshot", side_effect=_slow_download):
        resp1 = client.post("/api/app-data-backup/snapshots/999/restore")
        assert resp1.status_code == 200

        resp2 = client.post("/api/app-data-backup/snapshots/1000/restore")
        assert resp2.status_code == 409

        release.append(True)
        _wait_for_restore_status(("done", "error"))
