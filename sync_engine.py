import hashlib
import logging
import os
import threading
import time
from collections import OrderedDict

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

import store

logger = logging.getLogger(__name__)

CYCLE_INTERVAL = 10

MAX_CYCLE_FAILURES = 5

CYCLE_BACKOFF_BASE = 10
MAX_CYCLE_BACKOFF = 300

STABILITY_CHECK_DELAY = 5
MAX_WAIT = 60

QUIET_WINDOW = 5
MAX_CYCLE_WAIT = 30

_IGNORED_PREFIXES = ("tgv_upload_", "tgv_dl_")
_IGNORED_NAMES = {"thumbs.db", "desktop.ini", ".ds_store", ".git", ".svn"}

_start_upload_fn = None

_observers = {}
_observers_guard = threading.Lock()

_lifecycle_locks = {}
_lifecycle_locks_guard = threading.Lock()

def _pair_lifecycle_lock(pair_id):
    with _lifecycle_locks_guard:
        lock = _lifecycle_locks.get(pair_id)
        if lock is None:
            lock = threading.RLock()
            _lifecycle_locks[pair_id] = lock
        return lock

_last_change_time = {}
_last_change_guard = threading.Lock()

_pending_paths = {}
_pending_paths_guard = threading.Lock()

_in_flight_paths = {}

def _mark_in_flight(pair_id, path):
    with _pending_paths_guard:
        _in_flight_paths.setdefault(pair_id, set()).add(path)

def _clear_in_flight(pair_id, path):
    with _pending_paths_guard:
        paths = _in_flight_paths.get(pair_id)
        if paths:
            paths.discard(path)

_cycle_threads = {}
_cycle_threads_guard = threading.Lock()

_path_locks = OrderedDict()
_path_locks_guard = threading.Lock()
_PATH_LOCKS_MAX = 500

_folder_creation_locks = OrderedDict()
_folder_creation_locks_guard = threading.Lock()
_FOLDER_CREATION_LOCKS_MAX = 500

def _sync_transfer_semaphore():
    global _transfer_semaphore, _transfer_semaphore_size
    max_parallel = max(1, int(store.load_settings().get("max_parallel_transfers") or 3))
    if _transfer_semaphore is None or _transfer_semaphore_size != max_parallel:
        _transfer_semaphore = threading.BoundedSemaphore(max_parallel)
        _transfer_semaphore_size = max_parallel
    return _transfer_semaphore

_transfer_semaphore = None
_transfer_semaphore_size = None

def _path_lock(path):
    with _path_locks_guard:
        lock = _path_locks.get(path)
        if lock is None:
            if len(_path_locks) >= _PATH_LOCKS_MAX:
                _path_locks.popitem(last=False)
            lock = threading.Lock()
            _path_locks[path] = lock
        else:
            _path_locks.move_to_end(path)
        return lock

def _folder_creation_lock(pair_id, relative_path):

    key = (pair_id, relative_path)
    with _folder_creation_locks_guard:
        lock = _folder_creation_locks.get(key)
        if lock is None:
            if len(_folder_creation_locks) >= _FOLDER_CREATION_LOCKS_MAX:
                _folder_creation_locks.popitem(last=False)
            lock = threading.Lock()
            _folder_creation_locks[key] = lock
        else:
            _folder_creation_locks.move_to_end(key)
        return lock

def _should_ignore(filename):
    lower = filename.lower()
    if lower in _IGNORED_NAMES:
        return True
    if any(lower.startswith(prefix) for prefix in _IGNORED_PREFIXES):
        return True
    return False

def _is_under(path, root):
    path = os.path.abspath(path)
    root = os.path.abspath(root)
    return path == root or path.startswith(root + os.sep)

def _hash_file(path):
    hasher = hashlib.blake2b(digest_size=8)
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()

def _wait_until_stable(path):
    deadline = time.time() + MAX_WAIT
    try:
        last_size = os.path.getsize(path)
    except OSError:
        return False
    while time.time() < deadline:
        time.sleep(STABILITY_CHECK_DELAY)
        try:
            size = os.path.getsize(path)
        except OSError:
            return False
        if size == last_size:
            return True
        last_size = size
    return False

class _Handler(FileSystemEventHandler):
    def __init__(self, pair_id):
        self.pair_id = pair_id

    def _mark_dirty(self):
        with _last_change_guard:
            _last_change_time[self.pair_id] = time.time()

    def on_created(self, event):
        if not event.is_directory:
            self._mark_dirty()

    def on_modified(self, event):
        if not event.is_directory:
            self._mark_dirty()

    def on_moved(self, event):
        if not event.is_directory:
            self._mark_dirty()

def _scan_local_tree(local_path, exclude_dot_files=True):

    tree = []
    for root, dirs, filenames in os.walk(local_path):
        dirs[:] = [d for d in dirs if not _should_ignore(d) and not (exclude_dot_files and d.startswith("."))]
        for fn in filenames:
            if _should_ignore(fn):
                continue
            if exclude_dot_files and fn.startswith("."):
                continue
            full = os.path.join(root, fn)
            try:
                st = os.stat(full)
                tree.append({
                    "path": full,
                    "size": st.st_size,
                    "mtime": st.st_mtime,
                    "inode": st.st_ino,
                })
            except OSError:
                continue
    return tree

def _compute_deltas(current_local, previous_local, pair_id):

    deltas = {"renames": [], "additions": [], "changes": []}

    prev_by_inode = {e["inode"]: e for e in previous_local}
    curr_by_inode = {e["inode"]: e for e in current_local}
    prev_by_path = {e["path"]: e for e in previous_local}

    renamed_inodes = set()
    for inode, curr in curr_by_inode.items():
        prev = prev_by_inode.get(inode)
        if (
            prev and prev["path"] != curr["path"] and curr["path"] not in prev_by_path
            and prev["size"] == curr["size"]
        ):
            deltas["renames"].append({
                "inode": inode,
                "old_path": prev["path"],
                "new_path": curr["path"],
            })
            renamed_inodes.add(inode)

    for inode, curr in curr_by_inode.items():
        if inode in renamed_inodes:
            continue
        prev = prev_by_inode.get(inode)
        if prev is None or prev["path"] != curr["path"]:

            deltas["additions"].append(curr)
        else:

            if curr["size"] != prev["size"] or curr["mtime"] != prev["mtime"]:
                deltas["changes"].append(curr)

    return deltas

def _execute_deltas(deltas, pair_id, pair_config, is_initial_scan=False, root_local_path=None):
    skipped_paths = set()
    for rename in deltas["renames"]:
        _apply_rename(rename, pair_id)
    for change in deltas["changes"]:
        if _apply_change(change, pair_id, pair_config, is_initial_scan, root_local_path) is False:
            skipped_paths.add(change["path"])
    for addition in deltas["additions"]:
        if _apply_addition(addition, pair_id, pair_config, is_initial_scan, root_local_path) is False:
            skipped_paths.add(addition["path"])
    return skipped_paths

def _apply_rename(rename, pair_id):

    record = store.rename_sync_record(rename["old_path"], rename["new_path"])
    if not record:
        return
    if record.get("vault_file_id"):
        new_name = os.path.basename(rename["new_path"])
        old_name = os.path.basename(rename["old_path"])
        if new_name != old_name:
            store.update_file(record["vault_file_id"], {"name": new_name})

def _apply_change(change, pair_id, pair_config, is_initial_scan=False, root_local_path=None):
    path = change["path"]

    if not is_initial_scan and not _wait_until_stable(path):
        return
    try:
        content_hash = _hash_file(path)
    except OSError:
        return
    existing = store.find_sync_record(path, pair_id)
    if existing and existing.get("content_hash") == content_hash:
        try:
            st = os.stat(path)
            store.upsert_sync_record({**existing, "size_bytes": st.st_size, "mtime": st.st_mtime})
        except OSError:
            pass
        return

    mode = pair_config.get("reupload_mode", "flag")
    if mode == "flag" or not existing or not existing.get("vault_file_id"):
        if existing:
            store.upsert_sync_record({**existing, "content_hash": content_hash, "status": "changed"})
        return

    current_pair = store.find_sync_pair(pair_id)
    if not current_pair or current_pair.get("paused"):
        logger.info(f"Sync: skipping re-upload of {path} - pair {pair_id} is paused")
        return False
    vault_file_id = existing["vault_file_id"]
    lock = _path_lock(path)
    if not lock.acquire(blocking=False):
        return
    try:
        st = os.stat(path)
        size, mtime, inode = st.st_size, st.st_mtime, st.st_ino
    except OSError:
        lock.release()
        return

    def _on_done(record):
        try:

            uploaded_hash = record.get("content_hash") or record.get("versions", [{}])[0].get("content_hash")
            if mode == "version":
                store.upsert_sync_record({**existing, "size_bytes": size, "mtime": mtime,
                    "local_inode": inode, "content_hash": uploaded_hash,
                    "vault_file_id": vault_file_id, "last_synced_at": store._now(), "status": "synced"})
            elif mode == "soft_delete":
                old_file = store.find_file(vault_file_id)
                if old_file and not old_file.get("deleted"):
                    store.soft_delete_file(vault_file_id)
                store.upsert_sync_record({**existing, "size_bytes": size, "mtime": mtime,
                    "local_inode": inode, "content_hash": uploaded_hash,
                    "vault_file_id": record["id"], "pair_id": pair_id,
                    "last_synced_at": store._now(), "status": "synced"})
            else:
                store.upsert_sync_record({**existing, "size_bytes": size, "mtime": mtime,
                    "local_inode": inode, "content_hash": uploaded_hash,
                    "vault_file_id": record["id"], "pair_id": pair_id,
                    "last_synced_at": store._now(), "status": "synced"})
        except Exception as e:
            logger.exception(f"Failed to upsert sync record for {path} in _apply_change: {e}")
        finally:
            lock.release()
            semaphore.release()

    try:

        rel_path = os.path.relpath(path, root_local_path) if root_local_path else ""
        parent_rel_dir = os.path.dirname(rel_path)
        folder_id = _get_or_create_vault_folder(parent_rel_dir, pair_config, pair_id)
        if folder_id is None:
            logger.error(f"_apply_change: folder_id is None for {path}, pair_config.folder_id={pair_config.get('folder_id')}")
            lock.release()
            return

        folders = store.load_folders()
        folder_exists = any(f["id"] == folder_id for f in folders)
        if not folder_exists:
            logger.error(f"_apply_change: folder_id={folder_id} does not exist in folders table! Available folders: {[f['id'] for f in folders]}")
            lock.release()
            return

        semaphore = _sync_transfer_semaphore()
        semaphore.acquire()

        settings = store.load_settings()
        filename = os.path.basename(path)
        kwargs = {
            "on_done": _on_done, "skip_duplicate_check": True, "source": "sync",
            "relative_path": rel_path.replace(os.sep, "/"),
        }
        if mode == "version":
            kwargs["target_file_id"] = vault_file_id
        _start_upload_fn(path, filename, folder_id,
            settings.get("max_chunk_size_bytes") or 1_900_000_000, **kwargs)
    except OSError:
        lock.release()
        semaphore.release()

def _apply_addition(addition, pair_id, pair_config, is_initial_scan=False, root_local_path=None):

    path = addition["path"]
    existing = store.find_sync_record(path, pair_id)
    if existing:
        existing_inode = existing.get("local_inode")
        if existing_inode is not None and existing_inode == addition["inode"]:
            return

    if not is_initial_scan and not _wait_until_stable(path):
        return
    return _queue_upload(path, pair_id, pair_config, root_local_path)

def _queue_upload(path, pair_id, pair_config, root_local_path):

    pair = store.find_sync_pair(pair_id)
    if not pair or pair.get("paused"):
        logger.info(f"Sync: skipping upload of {path} - pair {pair_id} is paused")
        return False
    lock = _path_lock(path)
    if not lock.acquire(blocking=False):
        return
    filename = os.path.basename(path)

    rel_path = os.path.relpath(path, root_local_path)
    parent_rel_dir = os.path.dirname(rel_path)
    folder_id = _get_or_create_vault_folder(parent_rel_dir, pair_config, pair_id)
    if folder_id is None:
        logger.error(f"_queue_upload: folder_id is None for {path}, pair_config.folder_id={pair_config.get('folder_id')}")
        lock.release()
        return

    folders = store.load_folders()
    folder_exists = any(f["id"] == folder_id for f in folders)
    if not folder_exists:
        logger.error(f"_queue_upload: folder_id={folder_id} does not exist in folders table! Available folders: {[f['id'] for f in folders]}")
        lock.release()
        return

    settings = store.load_settings()
    max_chunk_size = settings.get("max_chunk_size_bytes") or 1_900_000_000

    try:
        st = os.stat(path)
        size = st.st_size
        mtime = st.st_mtime
        inode = st.st_ino
    except OSError:
        lock.release()
        return

    def _on_done(record):
        try:

            content_hash = record.get("content_hash") or record.get("versions", [{}])[0].get("content_hash")
            store.upsert_sync_record({
                "local_path": path, "size_bytes": size, "mtime": mtime,
                "local_inode": inode, "content_hash": content_hash,
                "vault_file_id": record["id"], "pair_id": pair_id,
                "last_synced_at": store._now(), "status": "synced",
            })
        except Exception as e:
            logger.exception(f"Failed to upsert sync record for {path}: {e}")
        finally:
            _clear_in_flight(pair_id, path)
            lock.release()
            semaphore.release()

    def _on_duplicate(duplicate):

        try:
            if duplicate is not None:
                store.upsert_sync_record({
                    "local_path": path, "size_bytes": size, "mtime": mtime,
                    "local_inode": inode, "content_hash": duplicate.get("content_hash"),
                    "vault_file_id": duplicate["id"], "pair_id": pair_id,
                    "last_synced_at": store._now(), "status": "synced",
                })
                logger.info(f"Sync: {path} already in the vault as {duplicate['id']} - linked, not re-uploaded")
        except Exception as e:
            logger.exception(f"Failed to upsert sync record for duplicate {path}: {e}")
        finally:
            _clear_in_flight(pair_id, path)
            lock.release()
            semaphore.release()

    try:

        pair = store.find_sync_pair(pair_id)
        if not pair or pair.get("paused"):
            logger.info(f"Sync: skipping upload of {path} - pair {pair_id} is paused")
            lock.release()
            return False

        semaphore = _sync_transfer_semaphore()
        semaphore.acquire()

        _mark_in_flight(pair_id, path)
        _start_upload_fn(
            path, filename, folder_id, max_chunk_size,

            on_done=_on_done, on_duplicate=_on_duplicate, skip_duplicate_check=False, source="sync",
            relative_path=rel_path.replace(os.sep, "/"),
        )
    except OSError:

        _clear_in_flight(pair_id, path)
        lock.release()
        semaphore.release()

_vault_folder_cache = {}
_vault_folder_cache_guard = threading.Lock()

def _get_or_create_vault_folder(relative_dir, pair_config, pair_id):

    cache_key = (pair_id, relative_dir.replace(os.sep, "/") if relative_dir else "")

    with _vault_folder_cache_guard:
        if cache_key in _vault_folder_cache:
            return _vault_folder_cache[cache_key]

    root_folder_id = pair_config.get("folder_id")

    folders = store.load_folders()
    root_exists = any(f["id"] == root_folder_id for f in folders)
    if not root_exists:
        logger.error(f"_get_or_create_vault_folder: root_folder_id={root_folder_id} does not exist in folders table! Available: {[f['id'] for f in folders]}")
        return None

    if not cache_key[1]:

        with _vault_folder_cache_guard:
            _vault_folder_cache[cache_key] = root_folder_id
        return root_folder_id

    parts = cache_key[1].split("/")
    current_parent_id = root_folder_id
    current_path = ""

    for part in parts:
        current_path = f"{current_path}/{part}" if current_path else part
        sub_cache_key = (pair_id, current_path)

        with _vault_folder_cache_guard:
            if sub_cache_key in _vault_folder_cache:
                current_parent_id = _vault_folder_cache[sub_cache_key]
                continue

        lock = _folder_creation_lock(pair_id, current_path)
        with lock:

            with _vault_folder_cache_guard:
                if sub_cache_key in _vault_folder_cache:
                    current_parent_id = _vault_folder_cache[sub_cache_key]
                    continue

            folders = store.load_folders()
            existing = next((f for f in folders
                            if f.get("parent_id") == current_parent_id
                            and f["name"] == part
                            and not f.get("deleted", False)), None)

            if existing:
                current_parent_id = existing["id"]
            else:

                new_folder, error = store.create_folder(part, current_parent_id)
                if error or not new_folder:
                    logger.warning(f"Failed to create Vault folder '{part}' under {current_parent_id}: {error}, falling back to root folder {root_folder_id}")

                    current_parent_id = root_folder_id
                else:
                    current_parent_id = new_folder["id"]

            with _vault_folder_cache_guard:
                _vault_folder_cache[sub_cache_key] = current_parent_id

    return current_parent_id

def _is_dirty(pair_id):
    with _last_change_guard:
        return pair_id in _last_change_time

def _clear_dirty(pair_id):
    with _last_change_guard:
        _last_change_time.pop(pair_id, None)

def _wait_for_quiet(pair_id):

    deadline = time.time() + MAX_CYCLE_WAIT
    while time.time() < deadline:
        with _last_change_guard:
            last = _last_change_time.get(pair_id)
        if last is None or (time.time() - last) >= QUIET_WINDOW:
            return True
        time.sleep(2)
    return False

def _cycle_loop(pair_id, local_path):

    is_initial_scan = True
    consecutive_failures = 0
    while True:
        try:
            if is_initial_scan:

                logger.info(f"Sync cycle: starting initial scan for pair {pair_id}")
            else:
                time.sleep(CYCLE_INTERVAL)
            pair = store.find_sync_pair(pair_id)
            if not pair or pair.get("paused"):
                logger.info(f"Sync cycle: pair {pair_id} paused or deleted, stopping")
                return
            if not is_initial_scan and not _is_dirty(pair_id):
                continue
            logger.info(f"Sync cycle: waiting for quiet period for pair {pair_id}")
            _wait_for_quiet(pair_id)
            logger.info(f"Sync cycle: running cycle for pair {pair_id} (initial={is_initial_scan})")
            _run_cycle(pair_id, local_path, is_initial_scan)
            logger.info(f"Sync cycle: completed cycle for pair {pair_id}")
            is_initial_scan = False
            consecutive_failures = 0
        except Exception:
            consecutive_failures += 1
            logger.exception(f"Sync cycle: error in cycle loop for pair {pair_id} (failure {consecutive_failures}/{MAX_CYCLE_FAILURES})")
            if consecutive_failures >= MAX_CYCLE_FAILURES:
                logger.error(f"Sync cycle: pair {pair_id} exceeded max consecutive failures ({MAX_CYCLE_FAILURES}), stopping cycle thread")
                return

            backoff = min(CYCLE_BACKOFF_BASE * (2 ** (consecutive_failures - 1)), MAX_CYCLE_BACKOFF)
            logger.info(f"Sync cycle: backing off for {backoff}s before retry")
            time.sleep(backoff)

def _run_cycle(pair_id, local_path, is_initial_scan=False):

    pair = store.find_sync_pair(pair_id)
    if not pair or pair.get("paused"):
        return
    if not os.path.isdir(local_path):
        return

    current_tree = _scan_local_tree(local_path, exclude_dot_files=pair.get("exclude_dot_files", True))
    previous_tree = store.load_local_tree(pair_id)

    logger.info(f"Sync cycle: current_tree={len(current_tree)}, previous_tree={len(previous_tree)}")

    deltas = _compute_deltas(current_tree, previous_tree, pair_id)

    logger.info(f"Sync cycle: deltas for {pair_id}: additions={len(deltas.get('additions', []))}, changes={len(deltas.get('changes', []))}, renames={len(deltas.get('renames', []))}")

    with _pending_paths_guard:
        _pending_paths[pair_id] = [
            item["path"] for item in deltas.get("additions", []) + deltas.get("changes", [])
        ]

    skipped_paths = set()
    if any(deltas.values()):
        skipped_paths = _execute_deltas(deltas, pair_id, pair, is_initial_scan, local_path)

    tree_to_save = [entry for entry in current_tree if entry["path"] not in skipped_paths]
    store.save_local_tree(pair_id, tree_to_save)
    _clear_dirty(pair_id)

def _stop_watching(pair_id):
    with _pair_lifecycle_lock(pair_id):
        with _observers_guard:
            observer = _observers.pop(pair_id, None)
        if observer is not None:
            observer.stop()
            observer.join(timeout=5)

        with _cycle_threads_guard:
            _cycle_threads.pop(pair_id, None)

def _start_watching(pair_id, local_path):

    with _pair_lifecycle_lock(pair_id):
        _stop_watching(pair_id)
        if not os.path.isdir(local_path):
            return

        observer = Observer()
        observer.schedule(_Handler(pair_id), local_path, recursive=True)
        observer.start()
        with _observers_guard:
            _observers[pair_id] = observer

        with _last_change_guard:
            _last_change_time[pair_id] = time.time()

        thread = threading.Thread(target=_cycle_loop, args=(pair_id, local_path), daemon=True)
        thread.start()
        with _cycle_threads_guard:
            _cycle_threads[pair_id] = thread

def is_watching(pair_id):
    with _observers_guard:
        return pair_id in _observers

def shutdown():

    logger.info("Shutting down sync engine...")
    for pair_id in list(_observers.keys()):
        _stop_watching(pair_id)
    logger.info("Sync engine shutdown complete")

def init(start_upload_fn):
    global _start_upload_fn
    _start_upload_fn = start_upload_fn
    for pair in store.list_sync_pairs():

        folder_id = pair.get("folder_id")
        if not pair.get("paused") and folder_id:
            folders = store.load_folders()
            folder = next((f for f in folders if f["id"] == folder_id), None)
            if folder and not folder.get("deleted"):
                _start_watching(pair["id"], pair["local_path"])
            else:
                logger.warning(f"Sync pair {pair['id']} has invalid folder_id={folder_id}, not starting watcher")
        elif not pair.get("paused"):
            logger.warning(f"Sync pair {pair['id']} has no folder_id, not starting watcher")

def pair_created(pair):
    if not pair.get("paused"):
        _start_watching(pair["id"], pair["local_path"])

def pair_updated(pair):
    if not pair.get("paused"):
        _start_watching(pair["id"], pair["local_path"])
    else:
        _stop_watching(pair["id"])

def pair_deleted(pair_id):
    _stop_watching(pair_id)

def status():
    pairs = store.list_sync_pairs()
    sync_state = store.load_sync_state()

    files = []
    for key, record in sync_state.items():
        files.append({
            "sync_pair_id": record.get("pair_id"),
            "local_path": record.get("local_path"),
            "status": record.get("status", "synced"),
            "size_bytes": record.get("size_bytes"),
            "mtime": record.get("mtime"),
            "content_hash": record.get("content_hash"),
            "vault_file_id": record.get("vault_file_id"),
            "last_synced_at": record.get("last_synced_at"),
        })
    with _pending_paths_guard:
        pending_paths_snapshot = dict(_pending_paths)
        in_flight_snapshot = {pid: set(paths) for pid, paths in _in_flight_paths.items()}

    def _pending_count_for(pair_id):

        paths = set(pending_paths_snapshot.get(pair_id, []))
        paths |= in_flight_snapshot.get(pair_id, set())
        if not paths:
            return 0

        return sum(
            1 for path in paths
            if sync_state.get(f"{pair_id}:{path}", {}).get("status") != "synced"
        )

    return {
        "pairs": [
            {**p, "watching": is_watching(p["id"]), "pending_count": _pending_count_for(p["id"])}
            for p in pairs
        ],
        "files": files,
    }
