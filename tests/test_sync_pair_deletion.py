from unittest.mock import patch

import pytest

import app
import shared
import store
import telegram_client
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

def _make_folder(isolated_store):
    folder, error = isolated_store.create_folder("Test")
    assert error is None
    return folder["id"]

def test_delete_sync_pair_does_not_sweep_up_sibling_pair_with_shared_prefix(client, isolated_store, tmp_path):

    sync_dir = tmp_path / "Sync"
    sync_dir.mkdir()
    sync2_dir = tmp_path / "Sync2"
    sync2_dir.mkdir()
    folder_id = _make_folder(isolated_store)

    pair = isolated_store.add_sync_pair(str(sync_dir), folder_id)
    other_pair = isolated_store.add_sync_pair(str(sync2_dir), folder_id)

    other_upload_id = "up_other"
    shared.uploads[other_upload_id] = {"source": "sync", "status": "done"}
    shared.upload_retry_info[other_upload_id] = {"file_path": str(sync2_dir / "video.mp4")}

    resp = client.delete(f"/api/sync/pairs/{pair['id']}")
    assert resp.status_code == 200

    assert other_upload_id in shared.uploads
    assert other_upload_id in shared.upload_retry_info

    assert isolated_store.find_sync_pair(other_pair["id"]) is not None

def test_delete_sync_pair_forget_cancels_active_upload_instead_of_popping_it(client, isolated_store, tmp_path):
    sync_dir = tmp_path / "Sync"
    sync_dir.mkdir()
    folder_id = _make_folder(isolated_store)
    pair = isolated_store.add_sync_pair(str(sync_dir), folder_id)

    upload_id = "up_active"
    cancel_token = telegram_client.CancelToken()
    shared.uploads[upload_id] = {"source": "sync", "status": "uploading"}
    shared.upload_retry_info[upload_id] = {"file_path": str(sync_dir / "video.mp4")}
    shared.upload_cancel_tokens[upload_id] = cancel_token

    resp = client.delete(f"/api/sync/pairs/{pair['id']}")
    assert resp.status_code == 200

    assert upload_id in shared.uploads
    assert upload_id in shared.upload_retry_info

    assert cancel_token.is_cancelled() is True
    assert cancel_token.should_forget() is True

def test_delete_sync_pair_removes_already_terminal_upload_directly(client, isolated_store, tmp_path):
    sync_dir = tmp_path / "Sync"
    sync_dir.mkdir()
    folder_id = _make_folder(isolated_store)
    pair = isolated_store.add_sync_pair(str(sync_dir), folder_id)

    upload_id = "up_done"
    shared.uploads[upload_id] = {"source": "sync", "status": "done"}
    shared.upload_retry_info[upload_id] = {"file_path": str(sync_dir / "video.mp4")}

    resp = client.delete(f"/api/sync/pairs/{pair['id']}")
    assert resp.status_code == 200

    assert upload_id not in shared.uploads
    assert upload_id not in shared.upload_retry_info

def test_with_sync_pairs_lock_is_reentrant(isolated_store):

    import threading

    done = threading.Event()
    result = {}

    def _nested():
        try:

            pair = isolated_store.with_sync_pairs_lock(
                lambda: isolated_store.add_sync_pair("/tmp/reentrant", None)
            )
            result["created"] = pair["id"]
            result["deleted"] = isolated_store.with_sync_pairs_lock(
                lambda: isolated_store.delete_sync_pair(pair["id"])
            )
        except Exception as e:
            result["error"] = repr(e)
        done.set()

    threading.Thread(target=_nested, daemon=True).start()
    assert done.wait(10), "with_sync_pairs_lock deadlocked on a nested sync-pair call"
    assert "error" not in result, result
    assert result["deleted"] is True

def test_the_sync_pairs_lock_is_an_rlock(isolated_store):

    import threading

    assert isinstance(isolated_store._SYNC_PAIRS_LOCK, type(threading.RLock()))
