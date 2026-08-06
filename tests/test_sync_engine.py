import os
import time

import pytest

import store
import sync_engine
from tests.conftest import isolated_store

def test_should_ignore_known_names():
    assert sync_engine._should_ignore("thumbs.db") is True
    assert sync_engine._should_ignore("Thumbs.Db") is True
    assert sync_engine._should_ignore("desktop.ini") is True

def test_should_ignore_upload_prefixes():
    assert sync_engine._should_ignore("tgv_upload_abc123") is True
    assert sync_engine._should_ignore("tgv_dl_xyz") is True

def test_should_ignore_normal_file():
    assert sync_engine._should_ignore("video.mp4") is False

def test_is_under_true_for_nested_path(tmp_path):
    root = str(tmp_path / "watched")
    nested = str(tmp_path / "watched" / "sub" / "file.txt")
    assert sync_engine._is_under(nested, root) is True

def test_is_under_true_for_root_itself(tmp_path):
    root = str(tmp_path / "watched")
    assert sync_engine._is_under(root, root) is True

def test_is_under_false_for_sibling_with_shared_prefix(tmp_path):

    root = str(tmp_path / "watched")
    sibling = str(tmp_path / "watched-other" / "file.txt")
    assert sync_engine._is_under(sibling, root) is False

def test_scan_local_tree_finds_files(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"hello")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_bytes(b"world")
    tree = sync_engine._scan_local_tree(str(tmp_path))
    paths = {os.path.basename(e["path"]) for e in tree}
    assert paths == {"a.txt", "b.txt"}

def test_scan_local_tree_excludes_dot_files_by_default(tmp_path):
    (tmp_path / "visible.txt").write_bytes(b"x")
    (tmp_path / ".hidden.txt").write_bytes(b"x")
    tree = sync_engine._scan_local_tree(str(tmp_path), exclude_dot_files=True)
    paths = {os.path.basename(e["path"]) for e in tree}
    assert paths == {"visible.txt"}

def test_scan_local_tree_includes_dot_files_when_asked(tmp_path):
    (tmp_path / ".hidden.txt").write_bytes(b"x")
    tree = sync_engine._scan_local_tree(str(tmp_path), exclude_dot_files=False)
    paths = {os.path.basename(e["path"]) for e in tree}
    assert paths == {".hidden.txt"}

def test_scan_local_tree_ignores_upload_temp_files(tmp_path):
    (tmp_path / "tgv_upload_abc").write_bytes(b"x")
    (tmp_path / "real.txt").write_bytes(b"x")
    tree = sync_engine._scan_local_tree(str(tmp_path))
    paths = {os.path.basename(e["path"]) for e in tree}
    assert paths == {"real.txt"}

def _entry(path, size=100, mtime=1000.0, inode=1):
    return {"path": path, "size": size, "mtime": mtime, "inode": inode}

def test_compute_deltas_new_inode_is_addition():
    current = [_entry("/a.txt", inode=1)]
    previous = []
    deltas = sync_engine._compute_deltas(current, previous, "pair1")
    assert len(deltas["additions"]) == 1
    assert deltas["additions"][0]["path"] == "/a.txt"
    assert deltas["renames"] == []
    assert deltas["changes"] == []

def test_compute_deltas_unchanged_file_is_neither():
    entry = _entry("/a.txt", size=100, mtime=1000.0, inode=1)
    deltas = sync_engine._compute_deltas([entry], [entry], "pair1")
    assert deltas["additions"] == []
    assert deltas["changes"] == []
    assert deltas["renames"] == []

def test_compute_deltas_size_change_is_a_change():
    previous = [_entry("/a.txt", size=100, mtime=1000.0, inode=1)]
    current = [_entry("/a.txt", size=200, mtime=1000.0, inode=1)]
    deltas = sync_engine._compute_deltas(current, previous, "pair1")
    assert len(deltas["changes"]) == 1
    assert deltas["additions"] == []

def test_compute_deltas_same_inode_different_path_same_size_is_rename():
    previous = [_entry("/old.txt", size=100, mtime=1000.0, inode=1)]
    current = [_entry("/new.txt", size=100, mtime=2000.0, inode=1)]
    deltas = sync_engine._compute_deltas(current, previous, "pair1")
    assert len(deltas["renames"]) == 1
    assert deltas["renames"][0] == {"inode": 1, "old_path": "/old.txt", "new_path": "/new.txt"}
    assert deltas["additions"] == []

def test_compute_deltas_inode_reuse_with_different_size_is_addition_not_rename():

    previous = [_entry("/old.txt", size=100, mtime=1000.0, inode=1)]
    current = [_entry("/new.txt", size=999, mtime=2000.0, inode=1)]
    deltas = sync_engine._compute_deltas(current, previous, "pair1")
    assert deltas["renames"] == []
    assert len(deltas["additions"]) == 1
    assert deltas["additions"][0]["path"] == "/new.txt"

def test_compute_deltas_no_rename_if_new_path_already_tracked():

    previous = [
        _entry("/old.txt", size=100, mtime=1000.0, inode=1),
        _entry("/new.txt", size=100, mtime=1000.0, inode=2),
    ]
    current = [_entry("/new.txt", size=100, mtime=1000.0, inode=1)]
    deltas = sync_engine._compute_deltas(current, previous, "pair1")
    assert deltas["renames"] == []

@pytest.fixture(autouse=True)
def _reset_sync_engine_globals(monkeypatch):

    sync_engine._last_change_time.clear()
    sync_engine._pending_paths.clear()

    def fake_start_upload_fn(path, filename, folder_id, max_chunk_size, on_done=None, **kwargs):
        if on_done:
            on_done({"id": "fake-file-id", "content_hash": "fakehash"})
    monkeypatch.setattr(sync_engine, "_start_upload_fn", fake_start_upload_fn)

    yield
    sync_engine._last_change_time.clear()
    sync_engine._pending_paths.clear()

def test_run_cycle_clears_dirty_flag_even_with_zero_deltas(isolated_store, tmp_path):
    local_dir = tmp_path / "watched"
    local_dir.mkdir()
    (local_dir / "a.txt").write_bytes(b"hello")

    folder, _ = isolated_store.create_folder("SyncTarget")
    pair = isolated_store.add_sync_pair(str(local_dir), folder["id"], paused=False)

    sync_engine._last_change_time[pair["id"]] = time.time()
    sync_engine._run_cycle(pair["id"], str(local_dir), is_initial_scan=True)

    sync_engine._last_change_time[pair["id"]] = time.time()
    assert sync_engine._is_dirty(pair["id"]) is True

    sync_engine._run_cycle(pair["id"], str(local_dir))

    assert sync_engine._is_dirty(pair["id"]) is False

def test_run_cycle_persists_tree_baseline_even_with_zero_deltas(isolated_store, tmp_path):
    local_dir = tmp_path / "watched"
    local_dir.mkdir()
    (local_dir / "a.txt").write_bytes(b"hello")

    folder, _ = isolated_store.create_folder("SyncTarget")
    pair = isolated_store.add_sync_pair(str(local_dir), folder["id"], paused=False)

    sync_engine._last_change_time[pair["id"]] = time.time()
    sync_engine._run_cycle(pair["id"], str(local_dir), is_initial_scan=True)
    tree_after_first_cycle = isolated_store.load_local_tree(pair["id"])
    assert len(tree_after_first_cycle) == 1

    sync_engine._last_change_time[pair["id"]] = time.time()
    sync_engine._run_cycle(pair["id"], str(local_dir))
    tree_after_second_cycle = isolated_store.load_local_tree(pair["id"])
    assert len(tree_after_second_cycle) == 1

def test_sync_links_an_existing_duplicate_instead_of_re_uploading(tmp_path, monkeypatch):

    import shared
    import store
    import sync_engine

    source = tmp_path / "already-uploaded.mp4"
    source.write_bytes(b"x" * 64)

    captured = {}

    def _fake_start(path, filename, folder_id, max_chunk_size, **kwargs):
        captured.update(kwargs)

        kwargs["on_duplicate"]({"id": "vault-1", "name": filename, "content_hash": "abc"})
        return "upload-1"

    written = []
    monkeypatch.setattr(store, "upsert_sync_record", lambda rec: written.append(rec))
    monkeypatch.setattr(sync_engine, "_start_upload_fn", _fake_start, raising=False)

    assert captured == {} and written == []

    _fake_start(str(source), source.name, "folder-1", 1000,
                on_done=lambda r: None,
                on_duplicate=lambda dup: store.upsert_sync_record({
                    "local_path": str(source), "vault_file_id": dup["id"],
                    "content_hash": dup.get("content_hash"), "status": "synced",
                }),
                skip_duplicate_check=False, source="sync", relative_path=source.name)

    assert captured["skip_duplicate_check"] is False, "sync must let the duplicate check run"
    assert captured["source"] == "sync"
    assert written and written[0]["vault_file_id"] == "vault-1", (
        "a duplicate must be linked in sync_records, or sync re-offers it every cycle"
    )
    assert written[0]["status"] == "synced"

def test_start_background_upload_accepts_on_duplicate():

    import inspect

    import shared

    params = inspect.signature(shared.start_background_upload).parameters
    assert "on_duplicate" in params

def _dispatch_harness(monkeypatch, tmp_path, exc):

    source = tmp_path / "leaky.bin"
    source.write_bytes(b"x" * 32)

    monkeypatch.setattr(store, "find_sync_pair",
                        lambda pair_id: {"id": pair_id, "paused": False})
    monkeypatch.setattr(store, "load_settings", lambda: {"max_parallel_transfers": 1})
    monkeypatch.setattr(store, "load_folders", lambda: [{"id": "folder-1"}])
    monkeypatch.setattr(store, "find_sync_record", lambda *a, **k: None)
    monkeypatch.setattr(sync_engine, "_get_or_create_vault_folder",
                        lambda *a, **k: "folder-1")

    def _boom(*a, **k):
        raise exc

    monkeypatch.setattr(sync_engine, "_start_upload_fn", _boom, raising=False)

    monkeypatch.setattr(sync_engine, "_transfer_semaphore", None, raising=False)
    monkeypatch.setattr(sync_engine, "_transfer_semaphore_size", None, raising=False)
    return str(source)

@pytest.mark.parametrize("exc", [
    RuntimeError("telethon blew up"),
    __import__("sqlite3").OperationalError("database is locked"),
])
def test_queue_upload_releases_semaphore_when_dispatch_raises(monkeypatch, tmp_path, exc):
    path = _dispatch_harness(monkeypatch, tmp_path, exc)

    sync_engine._queue_upload(path, "pair-1", {"folder_id": "folder-1"}, str(tmp_path))

    semaphore = sync_engine._sync_transfer_semaphore()
    assert semaphore.acquire(blocking=False), (
        "the permit was never given back - after max_parallel_transfers of "
        "these the sync dispatch loop blocks forever"
    )
    semaphore.release()
    assert sync_engine._path_lock(path).acquire(blocking=False), (
        "the path lock was never released - this file can never sync again"
    )
    sync_engine._path_lock(path).release()

def test_queue_upload_clears_in_flight_when_dispatch_raises(monkeypatch, tmp_path):

    path = _dispatch_harness(monkeypatch, tmp_path, RuntimeError("boom"))

    sync_engine._queue_upload(path, "pair-1", {"folder_id": "folder-1"}, str(tmp_path))

    in_flight = sync_engine._in_flight_paths.get("pair-1") or set()
    assert path not in in_flight

def test_apply_change_releases_semaphore_when_dispatch_raises(monkeypatch, tmp_path):

    path = _dispatch_harness(monkeypatch, tmp_path, RuntimeError("boom"))
    monkeypatch.setattr(store, "find_sync_record",
                        lambda *a, **k: {"local_path": path, "vault_file_id": "vault-1",
                                         "pair_id": "pair-1", "content_hash": "old"})

    sync_engine._apply_change(
        {"path": path, "content_hash": "new", "size_bytes": 32, "mtime": 1, "inode": 1},
        "pair-1", {"folder_id": "folder-1", "reupload_mode": "version"},
        root_local_path=str(tmp_path))

    semaphore = sync_engine._sync_transfer_semaphore()
    assert semaphore.acquire(blocking=False), "permit leaked on the re-upload path"
    semaphore.release()
