import copy
import io
import json
import lzma
import os
import sqlite3
import sys
import tarfile
import tempfile
import threading
import time
import unicodedata
import uuid
import zipfile
from collections import OrderedDict
from datetime import datetime
from typing import Optional, List, Dict, Any

import sync_engine

def _app_dir():

    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))

APP_DIR = _app_dir()
DATA_DIR = os.path.join(APP_DIR, "data")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
DB_FILE = os.path.join(DATA_DIR, "vault.db")

DEFAULT_SETTINGS = {
    "api_id": None,
    "api_hash": None,
    "phone_number": None,
    "archive_chat_id": None,
    "archive_chat_title": None,
    "is_premium": False,
    "max_chunk_size_bytes": 1_900_000_000,
    "video_player_path": None,
    "external_video_player_enabled": False,
    "sync_pairs": [],
    "app_data_backup_enabled": False,
    "app_data_backup_check_on_boot": False,
    "app_data_backup_last_known_message_id": None,

    "app_data_backup_pending_changes": False,

    "app_data_backup_include_thumbnails": False,

    "close_to_tray": True,

    "max_upload_request_bytes": 64_000_000_000,

    "backfill_scanned_chat_id": None,
    "backfill_scanned_up_to_message_id": 0,
    "max_parallel_transfers": 3,

    "upload_parallel_workers": 8,
    "upload_part_size_kb": 0,
    "max_cache_bytes": 0,
    "sync_backoff_workers": 1,
    "download_parallel_workers": 8,

    "completed_uploads_persistence": "clear",

    "thumbnail_format": "jpeg",

    "thumbnail_quality": 75,

    "thumbnail_chroma_subsampling": "default",
}

_DB_LOCK = threading.RLock()
_INIT_DONE = False

_write_locks: dict = OrderedDict()
_write_locks_guard = threading.Lock()
_WRITE_LOCKS_MAX = 500

def _get_write_lock(path):
    with _write_locks_guard:
        lock = _write_locks.get(path)
        if lock is None:
            if len(_write_locks) >= _WRITE_LOCKS_MAX:
                _write_locks.popitem(last=False)
            lock = threading.Lock()
            _write_locks[path] = lock
        else:
            _write_locks.move_to_end(path)
        return lock

def _atomic_write(path, data):
    os.makedirs(DATA_DIR, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=DATA_DIR, prefix=os.path.basename(path) + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        with _get_write_lock(path):
            last_err = None
            for attempt in range(8):
                try:
                    os.replace(tmp_path, path)
                    return
                except PermissionError as e:
                    last_err = e
                    if attempt < 7:
                        time.sleep(0.02 * (attempt + 1))
            raise last_err
    except BaseException:
        os.remove(tmp_path)
        raise

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE, check_same_thread=False, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def _init_db():
    global _INIT_DONE
    if _INIT_DONE:
        return
    with _DB_LOCK:
        if _INIT_DONE:
            return
        os.makedirs(DATA_DIR, exist_ok=True)
        os.makedirs(CACHE_DIR, exist_ok=True)
        conn = _get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS folders (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    parent_id TEXT REFERENCES folders(id) ON DELETE SET NULL,
                    date_created TEXT NOT NULL,
                    date_modified TEXT NOT NULL,
                    deleted INTEGER NOT NULL DEFAULT 0,
                    date_deleted TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_folders_parent ON folders(parent_id);
                CREATE INDEX IF NOT EXISTS idx_folders_deleted ON folders(deleted);

                CREATE TABLE IF NOT EXISTS files (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    folder_id TEXT REFERENCES folders(id) ON DELETE SET NULL,
                    size_bytes INTEGER NOT NULL,
                    mime_type TEXT,
                    telegram_chat_id TEXT NOT NULL,
                    chunks_json TEXT NOT NULL,
                    cached_chunks_json TEXT NOT NULL,
                    date_uploaded TEXT NOT NULL,
                    date_modified TEXT NOT NULL,
                    deleted INTEGER NOT NULL DEFAULT 0,
                    date_deleted TEXT,
                    source TEXT DEFAULT 'app',
                    original_name TEXT,
                    meta_message_id TEXT,
                    starred_at TEXT,
                    last_opened_at TEXT,
                    versions_json TEXT NOT NULL,
                    current_version INTEGER NOT NULL DEFAULT 0,
                    content_hash TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_files_folder ON files(folder_id);
                CREATE INDEX IF NOT EXISTS idx_files_deleted ON files(deleted);
                CREATE INDEX IF NOT EXISTS idx_files_hash ON files(content_hash);

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sync_state (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );

                -- One row per in-progress background upload with a stable,
                -- resumable local_path - native drop / folder upload / sync
                -- (a real file the USER owns), or a plain HTTP file-picker/
                -- folder-drag-drop upload's own Flask temp file (an
                -- app-owned copy under data/, tracked via owns_local_path -
                -- see save_pending_upload's own docstring for why this
                -- corrects an earlier, too-broad "nothing to resume from"
                -- assumption about that second case). Deleted the moment
                -- the upload reaches ANY terminal state (done/cancelled/
                -- error) - a leftover row is only ever a sign the process
                -- died before getting there, which is exactly what the
                -- boot-time scan looks for. folder_id/target_file_id are
                -- deliberately plain TEXT, NOT foreign keys - after today's
                -- save_folders/save_files cascade-delete incident, no table
                -- should reference folders(id)/files(id) with ON DELETE
                -- unless it actually wants a delete over there to cascade
                -- here too.
                CREATE TABLE IF NOT EXISTS pending_uploads (
                    id TEXT PRIMARY KEY,
                    local_path TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    folder_id TEXT,
                    target_file_id TEXT,
                    source TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    max_chunk_size INTEGER NOT NULL,
                    telegram_chat_id TEXT NOT NULL,
                    chunks_json TEXT NOT NULL,
                    skip_duplicate_check INTEGER NOT NULL DEFAULT 0,
                    force INTEGER NOT NULL DEFAULT 0,
                    relative_path TEXT,
                    created_at TEXT NOT NULL,
                    owns_local_path INTEGER NOT NULL DEFAULT 0
                );

                -- Folder-upload files still waiting in the frontend's own
                -- concurrent queue when the app closes - NOT yet a
                -- pending_uploads row, since no background upload has
                -- started for them (see /api/folders/upload-tree's own
                -- comment: that route only walks the tree and returns this
                -- list, the frontend starts each one later, one at a
                -- time). Without this table a restart silently dropped
                -- the whole backlog with no trace. Written when
                -- upload-tree returns the list, deleted the moment each
                -- file's real upload actually starts (start-from-path) or
                -- the user dismisses it - never updated otherwise, so a
                -- leftover row just means "still queued, untouched" the
                -- same way it would have looked before a restart.
                -- folder_id is plain TEXT, same FK-avoidance reasoning as
                -- pending_uploads above. owns_local_path (added 2026-07-28,
                -- same meaning as pending_uploads' own column) - false for
                -- a folder-picker upload-tree file or a native OS drop
                -- (the user's own real file, never ours to delete), true
                -- for a browser drag-and-drop file/folder staged into a
                -- durable temp copy under DATA_DIR by
                -- /api/uploads/queued/stage specifically so it too has a
                -- real path to persist here before its own upload starts -
                -- that temp copy must be cleaned up on dismiss, unlike a
                -- user-owned path.
                CREATE TABLE IF NOT EXISTS queued_uploads (
                    id TEXT PRIMARY KEY,
                    file_path TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    folder_id TEXT,
                    relative_path TEXT,
                    created_at TEXT NOT NULL,
                    owns_local_path INTEGER NOT NULL DEFAULT 0
                );

                -- Completed uploads (finished successfully) - persisted when
                -- completed_uploads_persistence = "keep", cleared on restart
                -- when = "clear". Separate from pending_uploads because these
                -- are terminal (no resume path) and the frontend renders them
                -- differently (no Continue button, just Dismiss).
                CREATE TABLE IF NOT EXISTS completed_uploads (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    folder_id TEXT,
                    relative_path TEXT,
                    bytes_done INTEGER NOT NULL,
                    bytes_total INTEGER NOT NULL,
                    kind TEXT NOT NULL DEFAULT 'upload',
                    completed_at TEXT NOT NULL
                );
            """)
            conn.commit()

            existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(pending_uploads)")}
            if "owns_local_path" not in existing_cols:
                conn.execute("ALTER TABLE pending_uploads ADD COLUMN owns_local_path INTEGER NOT NULL DEFAULT 0")
                conn.commit()

            if "upload_file_id" not in existing_cols:
                conn.execute("ALTER TABLE pending_uploads ADD COLUMN upload_file_id TEXT")
                conn.execute("ALTER TABLE pending_uploads ADD COLUMN upload_part_size INTEGER")
                conn.execute("ALTER TABLE pending_uploads ADD COLUMN upload_parts_sent INTEGER NOT NULL DEFAULT 0")
                conn.commit()

            queued_cols = {row[1] for row in conn.execute("PRAGMA table_info(queued_uploads)")}
            if "owns_local_path" not in queued_cols:
                conn.execute("ALTER TABLE queued_uploads ADD COLUMN owns_local_path INTEGER NOT NULL DEFAULT 0")
                conn.commit()

            cur = conn.execute("SELECT COUNT(*) FROM settings")
            if cur.fetchone()[0] == 0:
                for k, v in DEFAULT_SETTINGS.items():
                    conn.execute(
                        "INSERT INTO settings (key, value_json) VALUES (?, ?)",
                        (k, json.dumps(v))
                    )
                conn.commit()

            _INIT_DONE = True
        finally:
            conn.close()

def _now():
    return datetime.now().isoformat(timespec="seconds")

def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row) if row else None

def _json_loads(s: str) -> Any:
    return json.loads(s) if s else None

def load_folders() -> List[dict]:
    _init_db()
    with _DB_LOCK:
        conn = _get_conn()
        try:
            rows = conn.execute("""
                SELECT id, name, parent_id, date_created, date_modified, deleted, date_deleted
                FROM folders ORDER BY name
            """).fetchall()
            return [_row_to_dict(r) for r in rows]
        finally:
            conn.close()

def save_folders(folders: List[dict]):

    _init_db()
    with _DB_LOCK:
        conn = _get_conn()
        try:
            existing_ids = {r[0] for r in conn.execute("SELECT id FROM folders")}
            new_ids = {f["id"] for f in folders}
            removed_ids = existing_ids - new_ids
            if removed_ids:
                conn.executemany("DELETE FROM folders WHERE id = ?", [(fid,) for fid in removed_ids])

            folder_map = {f["id"]: f for f in folders}
            inserted = set()
            def insert_folder(folder_id):
                if folder_id in inserted:
                    return
                f = folder_map[folder_id]
                pid = f.get("parent_id")
                if pid:
                    insert_folder(pid)
                conn.execute("""
                    INSERT INTO folders (id, name, parent_id, date_created, date_modified, deleted, date_deleted)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name=excluded.name, parent_id=excluded.parent_id,
                        date_created=excluded.date_created, date_modified=excluded.date_modified,
                        deleted=excluded.deleted, date_deleted=excluded.date_deleted
                """, (f["id"], f["name"], f.get("parent_id"), f["date_created"], f["date_modified"],
                      1 if f.get("deleted") else 0, f.get("date_deleted")))
                inserted.add(folder_id)

            for f in folders:
                insert_folder(f["id"])
            conn.commit()
        finally:
            conn.close()

def create_folder(name: str, parent_id: Optional[str] = None):
    name = str(name or "").strip()
    if not name:
        return None, "Name is required."
    folders = load_folders()
    if parent_id is not None:
        parent = next((f for f in folders if f["id"] == parent_id), None)
        if parent is None or parent["deleted"]:
            return None, "Parent folder not found."
    folder = {
        "id": uuid.uuid4().hex[:8],
        "name": name,
        "parent_id": parent_id,
        "date_created": _now(),
        "date_modified": _now(),
        "deleted": False,
        "date_deleted": None,
    }
    folders.append(folder)
    save_folders(folders)
    return folder, None

def get_or_create_folder(name: str, parent_id: Optional[str] = None):

    name = str(name or "").strip()
    if not name:
        return None, "Name is required."
    folders = load_folders()

    folded = unicodedata.normalize("NFC", name)
    existing = next(
        (f for f in folders
         if f["parent_id"] == parent_id
         and unicodedata.normalize("NFC", f["name"]) == folded
         and not f["deleted"]), None
    )
    if existing is not None:
        return existing, None
    return create_folder(name, parent_id)

def _find_folder(folders: List[dict], folder_id: str):
    return next((f for f in folders if f["id"] == folder_id), None)

def _descendant_ids(folders: List[dict], folder_id: str):
    ids = set()
    frontier = [folder_id]
    while frontier:
        current_id = frontier.pop()
        for f in folders:
            if f["parent_id"] == current_id and f["id"] not in ids:
                ids.add(f["id"])
                frontier.append(f["id"])
    return ids

def _is_self_or_descendant(folders: List[dict], candidate_id: str, target_id: str):
    return candidate_id == target_id or candidate_id in _descendant_ids(folders, target_id)

def update_folder(folder_id: str, fields: dict):
    folders = load_folders()
    folder = _find_folder(folders, folder_id)
    if folder is None:
        return None, "Folder not found."
    if "name" in fields:
        name = str(fields["name"] or "").strip()
        if not name:
            return None, "Name is required."
        folder["name"] = name
    if "parent_id" in fields:
        new_parent_id = fields["parent_id"]
        if new_parent_id is not None:
            if _is_self_or_descendant(folders, new_parent_id, folder_id):
                return None, "Can't move a folder into itself or its own subfolder."
            parent = _find_folder(folders, new_parent_id)
            if parent is None or parent["deleted"]:
                return None, "Parent folder not found."
        folder["parent_id"] = new_parent_id
    folder["date_modified"] = _now()
    save_folders(folders)
    return folder, None

def soft_delete_folder(folder_id: str):
    folders = load_folders()
    folder = _find_folder(folders, folder_id)
    if folder is None:
        return False
    ids_to_delete = {folder_id} | _descendant_ids(folders, folder_id)
    now = _now()
    for f in folders:
        if f["id"] in ids_to_delete:
            f["deleted"] = True
            f["date_deleted"] = now
    save_folders(folders)
    files = load_files()
    changed = False
    for f in files:
        if f["folder_id"] in ids_to_delete and not f["deleted"]:
            f["deleted"] = True
            f["date_deleted"] = now
            changed = True
    if changed:
        save_files(files)
    return True

def restore_folder(folder_id: str):
    folders = load_folders()
    folder = _find_folder(folders, folder_id)
    if folder is None or not folder["deleted"]:
        return None, "Folder not found or not deleted."
    if folder["parent_id"] is not None:
        parent = _find_folder(folders, folder["parent_id"])
        if parent is None or parent["deleted"]:
            logger.warning(f"Restore folder {folder_id}: parent_id={folder['parent_id']} not found or deleted, reparenting to root")
            folder["parent_id"] = None
    now = _now()
    ids_to_restore = {folder_id} | _descendant_ids(folders, folder_id)
    restored_folders = []
    for f in folders:
        if f["id"] in ids_to_restore and f["deleted"]:
            f["deleted"] = False
            f["date_deleted"] = None
            f["date_modified"] = now
            restored_folders.append(f)
    save_folders(folders)
    files = load_files()
    restored_files = []
    for f in files:
        if f["folder_id"] in ids_to_restore and f["deleted"]:
            f["deleted"] = False
            f["date_deleted"] = None
            f["date_modified"] = now
            restored_files.append(f)
    if restored_files:
        save_files(files)
    return {"restored_folders": restored_folders, "restored_files": restored_files}, None

def permanent_delete_folder(folder_id: str):
    folders = load_folders()
    folder = _find_folder(folders, folder_id)
    if folder is None:
        return False, "Folder not found."
    ids_to_delete = {folder_id} | _descendant_ids(folders, folder_id)
    files = load_files()
    child_file_ids = [f["id"] for f in files if f["folder_id"] in ids_to_delete]
    for fid in child_file_ids:
        permanent_delete_file(fid)
    folders = [f for f in load_folders() if f["id"] not in ids_to_delete]
    save_folders(folders)
    return True, None

def descendant_folder_ids(folder_id: str):
    return _descendant_ids(load_folders(), folder_id)

def folder_summary(folder_id: str):

    folders = load_folders()
    files = load_files()
    descendant_ids = _descendant_ids(folders, folder_id)
    live_descendant_folders = [f for f in folders if f["id"] in descendant_ids and not f["deleted"]]
    scope_ids = {folder_id} | {f["id"] for f in live_descendant_folders}
    matching_files = [f for f in files if f["folder_id"] in scope_ids and not f["deleted"]]
    return {
        "file_count": len(matching_files),
        "folder_count": len(live_descendant_folders),
        "total_size": sum(f["size_bytes"] for f in matching_files),
    }

def _migrate_file_record(f: dict) -> dict:
    if "versions" not in f:
        f["versions"] = [{
            "chunks": f["chunks"],
            "size_bytes": f["size_bytes"],
            "mime_type": f.get("mime_type"),
            "cached_chunks": f.get("cached_chunks", [False] * len(f["chunks"])),
            "uploaded_at": f.get("date_uploaded", _now()),
            "content_hash": None,
            "has_thumbnail": False,
        }]
        f["current_version"] = 0
    if "original_name" not in f:
        f["original_name"] = None
    if "meta_message_id" not in f:
        f["meta_message_id"] = None
    return f

def load_files() -> List[dict]:
    _init_db()
    with _DB_LOCK:
        conn = _get_conn()
        try:
            rows = conn.execute("""
                SELECT id, name, folder_id, size_bytes, mime_type, telegram_chat_id,
                       chunks_json, cached_chunks_json, date_uploaded, date_modified,
                       deleted, date_deleted, source, original_name, meta_message_id,
                       starred_at, last_opened_at, versions_json, current_version, content_hash
                FROM files ORDER BY date_uploaded DESC
            """).fetchall()
            files = []
            for r in rows:
                f = _row_to_dict(r)
                f["chunks"] = _json_loads(f.pop("chunks_json"))
                f["cached_chunks"] = _json_loads(f.pop("cached_chunks_json"))
                f["versions"] = _json_loads(f.pop("versions_json"))
                f["deleted"] = bool(f["deleted"])
                f = _migrate_file_record(f)
                files.append(f)
            return files
        finally:
            conn.close()

def save_files(files: List[dict]):

    _init_db()
    with _DB_LOCK:
        conn = _get_conn()
        try:
            existing_ids = {r[0] for r in conn.execute("SELECT id FROM files")}
            new_ids = {f["id"] for f in files}
            removed_ids = existing_ids - new_ids
            if removed_ids:
                conn.executemany("DELETE FROM files WHERE id = ?", [(fid,) for fid in removed_ids])

            for f in files:
                conn.execute("""
                    INSERT INTO files (id, name, folder_id, size_bytes, mime_type, telegram_chat_id,
                        chunks_json, cached_chunks_json, date_uploaded, date_modified,
                        deleted, date_deleted, source, original_name, meta_message_id,
                        starred_at, last_opened_at, versions_json, current_version, content_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name=excluded.name, folder_id=excluded.folder_id,
                        size_bytes=excluded.size_bytes, mime_type=excluded.mime_type,
                        telegram_chat_id=excluded.telegram_chat_id,
                        chunks_json=excluded.chunks_json, cached_chunks_json=excluded.cached_chunks_json,
                        date_uploaded=excluded.date_uploaded, date_modified=excluded.date_modified,
                        deleted=excluded.deleted, date_deleted=excluded.date_deleted,
                        source=excluded.source, original_name=excluded.original_name,
                        meta_message_id=excluded.meta_message_id,
                        starred_at=excluded.starred_at, last_opened_at=excluded.last_opened_at,
                        versions_json=excluded.versions_json, current_version=excluded.current_version,
                        content_hash=excluded.content_hash
                """, (
                    f["id"], f["name"], f.get("folder_id"), f["size_bytes"], f.get("mime_type"),
                    f["telegram_chat_id"], json.dumps(f["chunks"]), json.dumps(f["cached_chunks"]),
                    f["date_uploaded"], f["date_modified"], 1 if f.get("deleted") else 0,
                    f.get("date_deleted"), f.get("source", "app"), f.get("original_name"),
                    f.get("meta_message_id"), f.get("starred_at"), f.get("last_opened_at"),
                    json.dumps(f["versions"]), f.get("current_version", 0), f.get("content_hash")
                ))
            conn.commit()
        finally:
            conn.close()

def current_version(file: dict):
    return file["versions"][file["current_version"]]

def _sync_current_version_mirror(file: dict):
    version = current_version(file)
    file["size_bytes"] = version["size_bytes"]
    file["mime_type"] = version["mime_type"]
    file["chunks"] = version["chunks"]
    file["cached_chunks"] = version["cached_chunks"]

def find_file(file_id: str):
    return next((f for f in load_files() if f["id"] == file_id), None)

def create_file(fields: dict):
    files = load_files()
    date_uploaded = _now()
    record = {
        "id": uuid.uuid4().hex[:8],
        "name": fields["name"],
        "folder_id": fields.get("folder_id"),
        "size_bytes": fields["size_bytes"],
        "mime_type": fields.get("mime_type"),
        "telegram_chat_id": fields["telegram_chat_id"],
        "chunks": fields["chunks"],
        "cached_chunks": [False] * len(fields["chunks"]),
        "date_uploaded": date_uploaded,
        "date_modified": _now(),
        "deleted": False,
        "date_deleted": None,
        "source": fields.get("source", "app"),
        "original_name": fields["name"],
        "meta_message_id": None,
        "starred_at": None,
        "last_opened_at": None,
        "versions": [{
            "chunks": fields["chunks"],
            "size_bytes": fields["size_bytes"],
            "mime_type": fields.get("mime_type"),
            "cached_chunks": [False] * len(fields["chunks"]),
            "uploaded_at": date_uploaded,
            "content_hash": fields.get("content_hash"),
            "has_thumbnail": bool(fields.get("has_thumbnail")),
        }],
        "current_version": 0,
        "content_hash": fields.get("content_hash"),
    }
    files.append(record)
    save_files(files)
    return record

def add_file_version(file_id: str, fields: dict):
    files = load_files()
    file = next((f for f in files if f["id"] == file_id), None)
    if file is None:
        return None, "File not found."
    file["versions"].append({
        "chunks": fields["chunks"],
        "size_bytes": fields["size_bytes"],
        "mime_type": fields.get("mime_type"),
        "cached_chunks": [False] * len(fields["chunks"]),
        "uploaded_at": _now(),
        "content_hash": fields.get("content_hash"),
        "has_thumbnail": bool(fields.get("has_thumbnail")),
    })
    file["current_version"] = len(file["versions"]) - 1
    _sync_current_version_mirror(file)
    file["date_modified"] = _now()
    save_files(files)
    return file, None

def find_duplicate_by_hash(content_hash: str):
    if content_hash is None:
        return None
    for file in load_files():
        if file["deleted"]:
            continue
        version = file["versions"][file["current_version"]]
        if version.get("content_hash") == content_hash:
            return file
    return None

def restore_file_version(file_id: str, version_index: int):
    files = load_files()
    file = next((f for f in files if f["id"] == file_id), None)
    if file is None:
        return None, "File not found."
    if not (0 <= version_index < len(file["versions"])):
        return None, "Version not found."
    file["current_version"] = version_index
    _sync_current_version_mirror(file)
    file["date_modified"] = _now()
    save_files(files)
    return file, None

def update_file(file_id: str, fields: dict):
    files = load_files()
    file = next((f for f in files if f["id"] == file_id), None)
    if file is None:
        return None, "File not found."
    if "name" in fields:
        name = str(fields["name"] or "").strip()
        if not name:
            return None, "Name is required."
        file["name"] = name
    if "folder_id" in fields:
        new_folder_id = fields["folder_id"]
        if new_folder_id is not None:
            folder = _find_folder(load_folders(), new_folder_id)
            if folder is None or folder["deleted"]:
                return None, "Folder not found."
        file["folder_id"] = new_folder_id
    if "meta_message_id" in fields:
        file["meta_message_id"] = fields["meta_message_id"]
    if "starred" in fields:
        file["starred_at"] = _now() if fields["starred"] else None
    file["date_modified"] = _now()
    save_files(files)
    return file, None

def mark_file_opened(file_id: str):
    files = load_files()
    file = next((f for f in files if f["id"] == file_id), None)
    if file is None:
        return None
    file["last_opened_at"] = _now()
    save_files(files)
    return file

def soft_delete_file(file_id: str):
    files = load_files()
    file = next((f for f in files if f["id"] == file_id), None)
    if file is None:
        return False
    file["deleted"] = True
    file["date_deleted"] = _now()
    save_files(files)
    return True

def restore_file(file_id: str):
    files = load_files()
    file = next((f for f in files if f["id"] == file_id), None)
    if file is None or not file["deleted"]:
        return None, "File not found or not deleted."
    if file["folder_id"] is not None:
        parent = _find_folder(load_folders(), file["folder_id"])
        if parent is None or parent["deleted"]:
            logger.warning(f"Restore file {file_id}: folder_id={file['folder_id']} not found or deleted, reparenting to root")
            file["folder_id"] = None
    file["deleted"] = False
    file["date_deleted"] = None
    file["date_modified"] = _now()
    save_files(files)
    return file, None

def permanent_delete_file(file_id: str):
    files = load_files()
    file = next((f for f in files if f["id"] == file_id), None)
    if file is None:
        return False
    for version_index, version in enumerate(file["versions"]):
        for i in range(len(version["chunks"])):
            try:
                os.remove(cache_path(file_id, version_index, i))
            except OSError:
                pass
            try:
                os.remove(partial_cache_path(file_id, version_index, i))
            except OSError:
                pass
        for ext in _THUMBNAIL_EXTS:
            try:
                os.remove(thumbnail_path_for_ext(file_id, version_index, ext))
            except OSError:
                pass
    remaining = [f for f in files if f["id"] != file_id]
    save_files(remaining)
    return True

def cache_path(file_id: str, version_index: int, chunk_index: int):
    return os.path.join(CACHE_DIR, f"{file_id}_v{version_index}_{chunk_index}")

def partial_cache_path(file_id: str, version_index: int, chunk_index: int):
    return cache_path(file_id, version_index, chunk_index) + ".partial"

def thumbnail_path_for_ext(file_id: str, version_index: int, ext: str):
    return os.path.join(CACHE_DIR, f"{file_id}_v{version_index}_thumb.{ext}")

def thumbnail_ext_for_format(fmt: str) -> str:

    return "avif" if fmt == "avif" else "jpg"

_THUMBNAIL_EXTS = ("avif", "jpg")

def find_thumbnail_path(file_id: str, version_index: int):

    for ext in _THUMBNAIL_EXTS:
        path = thumbnail_path_for_ext(file_id, version_index, ext)
        if os.path.exists(path):
            return path
    return None

def write_thumbnail_cache(file_id: str, version_index: int, data: bytes, ext: str):

    os.makedirs(CACHE_DIR, exist_ok=True)
    for other_ext in _THUMBNAIL_EXTS:
        if other_ext != ext:
            try:
                os.remove(thumbnail_path_for_ext(file_id, version_index, other_ext))
            except OSError:
                pass
    with open(thumbnail_path_for_ext(file_id, version_index, ext), "wb") as f:
        f.write(data)

def _is_thumbnail_cache_name(name: str) -> bool:
    return name.endswith("_thumb.avif") or name.endswith("_thumb.jpg")

def mark_chunk_cached(file_id: str, version_index: int, chunk_index: int):
    files = load_files()
    file = next((f for f in files if f["id"] == file_id), None)
    if file is None:
        return
    file["versions"][version_index]["cached_chunks"][chunk_index] = True
    if version_index == file["current_version"]:
        file["cached_chunks"][chunk_index] = True
    save_files(files)

def _iter_cache_dir_entries():
    try:
        entries = os.scandir(CACHE_DIR)
    except OSError:
        return
    with entries:
        for entry in entries:
            try:
                if entry.is_file():
                    yield entry
            except OSError:
                pass

def cache_disk_usage():
    total = 0
    for entry in _iter_cache_dir_entries():
        try:
            total += entry.stat().st_size
        except OSError:
            pass
    return total

def clear_cache():
    freed = cache_disk_usage()
    for entry in _iter_cache_dir_entries():
        try:
            os.remove(entry.path)
        except OSError:
            pass
    files = load_files()
    for file in files:
        for version in file["versions"]:
            version["cached_chunks"] = [False] * len(version["cached_chunks"])
        file["cached_chunks"] = list(file["versions"][file["current_version"]]["cached_chunks"])
    save_files(files)
    return freed

def prune_cache():
    settings = load_settings()
    max_bytes = int(settings.get("max_cache_bytes") or 0)
    if max_bytes <= 0:
        return 0
    current = cache_disk_usage()
    if current <= max_bytes:
        return 0
    entries_with_mtime = []
    for entry in _iter_cache_dir_entries():
        try:
            stat = entry.stat()
            entries_with_mtime.append((entry.path, stat.st_size, stat.st_mtime))
        except OSError:
            pass
    entries_with_mtime.sort(key=lambda x: x[2])
    freed = 0
    to_free = current - max_bytes
    for path, size, _mtime in entries_with_mtime:
        if freed >= to_free:
            break
        try:
            os.remove(path)
            freed += size
        except OSError:
            pass
    return freed

def build_app_data_snapshot(on_progress=None, include_thumbnails=True):

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:xz", preset=9 | lzma.PRESET_EXTREME) as tf:
        folders = load_folders()
        files = load_files()
        for name, content in (
            ("folders.json", json.dumps(folders, indent=2)),
            ("files.json", json.dumps(files, indent=2)),
        ):
            data = content.encode("utf-8")
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
        thumbnails = (
            [e for e in _iter_cache_dir_entries() if _is_thumbnail_cache_name(e.name)]
            if include_thumbnails else []
        )
        total = len(thumbnails)
        for i, entry in enumerate(thumbnails):
            tf.add(entry.path, arcname=f"cache/{entry.name}")

            if on_progress and (i % 20 == 0 or i == total - 1):
                on_progress(i + 1, total)
    return buf.getvalue()

def restore_app_data_snapshot(snapshot_bytes, on_progress=None):

    buf = io.BytesIO(snapshot_bytes)
    if zipfile.is_zipfile(buf):

        buf.seek(0)
        with zipfile.ZipFile(buf) as zf:
            names = set(zf.namelist())
            if "folders.json" in names:
                save_folders(json.loads(zf.read("folders.json")))
            if "files.json" in names:
                save_files(json.loads(zf.read("files.json")))
            os.makedirs(CACHE_DIR, exist_ok=True)
            for name in names:
                if name.startswith("cache/") and _is_thumbnail_cache_name(name):
                    with open(os.path.join(CACHE_DIR, os.path.basename(name)), "wb") as f:
                        f.write(zf.read(name))
        return

    buf.seek(0)
    with tarfile.open(fileobj=buf, mode="r:xz") as tf:

        members = tf.getmembers()
        members_by_name = {m.name: m for m in members}
        if "folders.json" in members_by_name:
            save_folders(json.loads(tf.extractfile(members_by_name["folders.json"]).read()))
        if "files.json" in members_by_name:
            save_files(json.loads(tf.extractfile(members_by_name["files.json"]).read()))
        os.makedirs(CACHE_DIR, exist_ok=True)
        thumbnail_members = [m for m in members if m.name.startswith("cache/") and _is_thumbnail_cache_name(m.name)]
        total = len(thumbnail_members)
        for i, member in enumerate(thumbnail_members):
            with open(os.path.join(CACHE_DIR, os.path.basename(member.name)), "wb") as f:
                f.write(tf.extractfile(member).read())
            if on_progress and (i % 20 == 0 or i == total - 1):

                on_progress(i + 1, total)

def _ensure_settings():
    _init_db()

def load_settings():
    _ensure_settings()
    with _DB_LOCK:
        conn = _get_conn()
        try:
            rows = conn.execute("SELECT key, value_json FROM settings").fetchall()
            settings = dict(DEFAULT_SETTINGS)
            for r in rows:
                settings[r["key"]] = _json_loads(r["value_json"])
            return settings
        finally:
            conn.close()

def save_settings_fields(fields: dict):
    _ensure_settings()
    settings = load_settings()
    settings.update(fields)
    with _DB_LOCK:
        conn = _get_conn()
        try:
            for k, v in fields.items():
                conn.execute(
                    "INSERT OR REPLACE INTO settings (key, value_json) VALUES (?, ?)",
                    (k, json.dumps(v))
                )
            conn.commit()
        finally:
            conn.close()
    return settings

def load_sync_state():
    _init_db()
    with _DB_LOCK:
        conn = _get_conn()
        try:
            rows = conn.execute("SELECT key, value_json FROM sync_state").fetchall()
            return {r["key"]: _json_loads(r["value_json"]) for r in rows}
        finally:
            conn.close()

def save_sync_state(state: dict):
    _init_db()
    with _DB_LOCK:
        conn = _get_conn()
        try:
            conn.execute("DELETE FROM sync_state")
            for k, v in state.items():
                conn.execute(
                    "INSERT INTO sync_state (key, value_json) VALUES (?, ?)",
                    (k, json.dumps(v))
                )
            conn.commit()
        finally:
            conn.close()

def migrate_from_json():

    _init_db()

    with _DB_LOCK:
        conn = _get_conn()
        try:
            cur = conn.execute("SELECT COUNT(*) FROM folders")
            if cur.fetchone()[0] > 0:
                return
        finally:
            conn.close()

    print("Migrating from JSON to SQLite...")
    _init_db()

    if os.path.exists(os.path.join(DATA_DIR, "folders.json")):
        with open(os.path.join(DATA_DIR, "folders.json"), "r", encoding="utf-8") as f:
            folders = json.load(f)
        save_folders(folders)
        print(f"  Migrated {len(folders)} folders")

    if os.path.exists(os.path.join(DATA_DIR, "files.json")):
        with open(os.path.join(DATA_DIR, "files.json"), "r", encoding="utf-8") as f:
            files = json.load(f)

        for file in files:
            _migrate_file_record(file)
        save_files(files)
        print(f"  Migrated {len(files)} files")

    if os.path.exists(os.path.join(DATA_DIR, "settings.json")):
        with open(os.path.join(DATA_DIR, "settings.json"), "r", encoding="utf-8") as f:
            settings = json.load(f)
        save_settings_fields(settings)
        print(f"  Migrated settings")

    if os.path.exists(os.path.join(DATA_DIR, "sync_state.json")):
        with open(os.path.join(DATA_DIR, "sync_state.json"), "r", encoding="utf-8") as f:
            sync_state = json.load(f)
        save_sync_state(sync_state)
        print(f"  Migrated sync state")

    print("Migration complete!")

def shutdown_sync_engine():

    sync_engine.shutdown()

def versioned_data_summary():
    files = load_files()
    messages_by_chat = {}
    files_affected = 0
    bytes_freed = 0
    for file in files:
        if len(file["versions"]) <= 1:
            continue
        files_affected += 1
        for vi, version in enumerate(file["versions"]):
            if vi == file["current_version"]:
                continue
            bytes_freed += version["size_bytes"]
            for chunk in version["chunks"]:
                chat_id = file["telegram_chat_id"]
                messages_by_chat.setdefault(chat_id, []).append(chunk["message_id"])
    return messages_by_chat, files_affected, bytes_freed

def apply_versioned_wipe():
    files = load_files()
    for file in files:
        if len(file["versions"]) <= 1:
            continue
        for vi, version in enumerate(file["versions"]):
            if vi == file["current_version"]:
                continue
            for chunk in version["chunks"]:
                try:
                    os.remove(cache_path(file["id"], vi, version["chunks"].index(chunk)))
                except OSError:
                    pass
        file["versions"] = [file["versions"][file["current_version"]]]
        file["current_version"] = 0
        _sync_current_version_mirror(file)
    save_files(files)

def everything_summary():
    files = load_files()
    folders = load_folders()
    total_files = len([f for f in files if not f["deleted"]])
    total_folders = len([f for f in folders if not f["deleted"]])
    total_size = sum(f["size_bytes"] for f in files if not f["deleted"])
    return {"total_files": total_files, "total_folders": total_folders, "total_size": total_size}

def apply_everything_wipe():
    save_folders([])
    save_files([])

_SYNC_PAIRS_LOCK = threading.RLock()

def with_sync_pairs_lock(fn):

    with _SYNC_PAIRS_LOCK:
        return fn()

def list_sync_pairs():
    settings = load_settings()
    return settings.get("sync_pairs", [])

def find_sync_pair(pair_id):
    pairs = list_sync_pairs()
    return next((p for p in pairs if p["id"] == pair_id), None)

def add_sync_pair(local_path, folder_id, paused=True, exclude_dot_files=True, reupload_mode="flag"):
    with _SYNC_PAIRS_LOCK:
        settings = load_settings()
        pairs = settings.get("sync_pairs", [])
        new_pair = {
            "id": uuid.uuid4().hex[:8],
            "local_path": local_path,
            "folder_id": folder_id,
            "paused": paused,
            "exclude_dot_files": exclude_dot_files,
            "reupload_mode": reupload_mode,
        }
        pairs.append(new_pair)
        save_settings_fields({"sync_pairs": pairs})
        return new_pair

def update_sync_pair(pair_id, fields):
    with _SYNC_PAIRS_LOCK:
        settings = load_settings()
        pairs = settings.get("sync_pairs", [])
        pair = next((p for p in pairs if p["id"] == pair_id), None)
        if pair is None:
            return None
        for k, v in fields.items():
            if k in ("paused", "exclude_dot_files", "reupload_mode", "local_path", "folder_id"):
                pair[k] = v
        save_settings_fields({"sync_pairs": pairs})
        return pair

def delete_sync_pair(pair_id):
    with _SYNC_PAIRS_LOCK:
        settings = load_settings()
        pairs = settings.get("sync_pairs", [])
        remaining = [p for p in pairs if p["id"] != pair_id]
        if len(remaining) == len(pairs):
            return False
        save_settings_fields({"sync_pairs": remaining})
        return True

def clear_sync_pair_state(pair_id, local_root):

    removed_state = 0
    state = load_sync_state()
    remaining_state = {k: v for k, v in state.items() if v.get("pair_id") != pair_id}
    removed_state = len(state) - len(remaining_state)
    if removed_state:
        save_sync_state(remaining_state)

    try:
        os.remove(_sync_tree_path(pair_id))
    except OSError:
        pass

    try:
        for name in os.listdir(DATA_DIR):
            if name.startswith(f"sync_tree_{pair_id}.json.") and name.endswith(".tmp"):
                try:
                    os.remove(os.path.join(DATA_DIR, name))
                except OSError:
                    pass
    except OSError:
        pass

    removed_pending = 0
    if local_root:
        for record in list_pending_uploads():
            if record["source"] == "sync" and record["local_path"].startswith(local_root):
                delete_pending_upload(record["id"])
                removed_pending += 1

    return {"sync_state_removed": removed_state, "pending_uploads_removed": removed_pending}

def _sync_tree_path(pair_id):
    return os.path.join(DATA_DIR, f"sync_tree_{pair_id}.json")

def save_local_tree(pair_id, tree):

    _atomic_write(_sync_tree_path(pair_id), tree)

def load_local_tree(pair_id):
    path = _sync_tree_path(pair_id)
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def find_sync_record(local_path, pair_id=None):
    state = load_sync_state()
    key = f"{pair_id}:{local_path}" if pair_id else local_path
    return state.get(key)

def upsert_sync_record(record):
    state = load_sync_state()
    key = f"{record['pair_id']}:{record['local_path']}"
    state[key] = record
    save_sync_state(state)

def rename_sync_record(old_path, new_path):

    _init_db()
    with _DB_LOCK:
        conn = _get_conn()
        try:

            rows = conn.execute(
                "SELECT key, value_json FROM sync_state WHERE json_extract(value_json, '$.local_path') = ?",
                (old_path,)
            ).fetchall()
            if not rows:
                return
            for row in rows:
                key = row["key"]
                value = json.loads(row["value_json"])
                value["local_path"] = new_path
                new_key = f"{value['pair_id']}:{new_path}"
                conn.execute("DELETE FROM sync_state WHERE key = ?", (key,))
                conn.execute(
                    "INSERT INTO sync_state (key, value_json) VALUES (?, ?)",
                    (new_key, json.dumps(value))
                )
            conn.commit()
        finally:
            conn.close()

def save_pending_upload(upload_id: str, fields: dict):
    _init_db()
    with _DB_LOCK:
        conn = _get_conn()
        try:
            conn.execute("""
                INSERT OR REPLACE INTO pending_uploads
                    (id, local_path, filename, folder_id, target_file_id, source,
                     size_bytes, max_chunk_size, telegram_chat_id, chunks_json,
                     skip_duplicate_check, force, relative_path, created_at, owns_local_path,
                     upload_file_id, upload_part_size, upload_parts_sent)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                upload_id, fields["local_path"], fields["filename"], fields.get("folder_id"),
                fields.get("target_file_id"), fields["source"], fields["size_bytes"],
                fields["max_chunk_size"], fields["telegram_chat_id"], json.dumps(fields.get("chunks") or []),
                1 if fields.get("skip_duplicate_check") else 0, 1 if fields.get("force") else 0,
                fields.get("relative_path"), _now(), 1 if fields.get("owns_local_path") else 0,
                None, None, 0,
            ))
            conn.commit()
        finally:
            conn.close()

def update_pending_upload_part_state(upload_id: str, file_id, part_size, parts_sent: int):
    _init_db()
    with _DB_LOCK:
        conn = _get_conn()
        try:
            conn.execute(
                "UPDATE pending_uploads SET upload_file_id = ?, upload_part_size = ?, upload_parts_sent = ? WHERE id = ?",
                (str(file_id) if file_id is not None else None, part_size, parts_sent, upload_id),
            )
            conn.commit()
        finally:
            conn.close()

def update_pending_upload_chunks(upload_id: str, chunks: list):
    _init_db()
    with _DB_LOCK:
        conn = _get_conn()
        try:
            conn.execute(
                "UPDATE pending_uploads SET chunks_json = ? WHERE id = ?",
                (json.dumps(chunks), upload_id),
            )
            conn.commit()
        finally:
            conn.close()

def delete_pending_upload(upload_id: str):
    _init_db()
    with _DB_LOCK:
        conn = _get_conn()
        try:
            conn.execute("DELETE FROM pending_uploads WHERE id = ?", (upload_id,))
            conn.commit()
        finally:
            conn.close()

def find_pending_upload(upload_id: str):
    _init_db()
    with _DB_LOCK:
        conn = _get_conn()
        try:
            row = conn.execute("SELECT * FROM pending_uploads WHERE id = ?", (upload_id,)).fetchone()
            if row is None:
                return None
            record = dict(row)
            record["chunks"] = _json_loads(record.pop("chunks_json")) or []
            record["skip_duplicate_check"] = bool(record["skip_duplicate_check"])
            record["force"] = bool(record["force"])
            record["owns_local_path"] = bool(record["owns_local_path"])
            return record
        finally:
            conn.close()

def list_pending_uploads():
    _init_db()
    with _DB_LOCK:
        conn = _get_conn()
        try:
            rows = conn.execute("SELECT * FROM pending_uploads ORDER BY created_at").fetchall()
            records = []
            for row in rows:
                record = dict(row)
                record["chunks"] = _json_loads(record.pop("chunks_json")) or []
                record["skip_duplicate_check"] = bool(record["skip_duplicate_check"])
                record["force"] = bool(record["force"])
                record["owns_local_path"] = bool(record["owns_local_path"])
                records.append(record)
            return records
        finally:
            conn.close()

def save_queued_uploads(records: list):

    if not records:
        return
    _init_db()
    with _DB_LOCK:
        conn = _get_conn()
        try:
            conn.executemany("""
                INSERT OR REPLACE INTO queued_uploads
                    (id, file_path, filename, folder_id, relative_path, created_at, owns_local_path)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [
                (
                    r["id"], r["file_path"], r["filename"], r.get("folder_id"), r.get("relative_path"), _now(),
                    1 if r.get("owns_local_path") else 0,
                )
                for r in records
            ])
            conn.commit()
        finally:
            conn.close()

def find_queued_upload(queued_id: str):
    _init_db()
    with _DB_LOCK:
        conn = _get_conn()
        try:
            row = conn.execute("SELECT * FROM queued_uploads WHERE id = ?", (queued_id,)).fetchone()
            if row is None:
                return None
            record = dict(row)
            record["owns_local_path"] = bool(record["owns_local_path"])
            return record
        finally:
            conn.close()

def delete_queued_upload(queued_id: str):

    _init_db()
    with _DB_LOCK:
        conn = _get_conn()
        try:
            row = conn.execute("SELECT file_path, owns_local_path FROM queued_uploads WHERE id = ?", (queued_id,)).fetchone()
            conn.execute("DELETE FROM queued_uploads WHERE id = ?", (queued_id,))
            conn.commit()
        finally:
            conn.close()
    if row is not None and row["owns_local_path"]:
        try:
            os.remove(row["file_path"])
        except OSError:
            pass

def list_queued_uploads():
    _init_db()
    with _DB_LOCK:
        conn = _get_conn()
        try:
            rows = conn.execute("SELECT * FROM queued_uploads ORDER BY created_at").fetchall()
            records = []
            for row in rows:
                record = dict(row)
                record["owns_local_path"] = bool(record["owns_local_path"])
                records.append(record)
            return records
        finally:
            conn.close()

def delete_queued_upload_row_only(queued_id: str):

    _init_db()
    with _DB_LOCK:
        conn = _get_conn()
        try:
            conn.execute("DELETE FROM queued_uploads WHERE id = ?", (queued_id,))
            conn.commit()
        finally:
            conn.close()

def save_completed_upload(record: dict):

    _init_db()
    with _DB_LOCK:
        conn = _get_conn()
        try:
            conn.execute("""
                INSERT OR REPLACE INTO completed_uploads
                (id, filename, folder_id, relative_path, bytes_done, bytes_total, kind, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record["id"], record["filename"], record.get("folder_id"),
                record.get("relative_path"), record["bytes_done"], record["bytes_total"],
                record.get("kind", "upload"), record.get("completed_at", _now()),
            ))
            conn.commit()
        finally:
            conn.close()

def list_completed_uploads():

    _init_db()
    with _DB_LOCK:
        conn = _get_conn()
        try:
            rows = conn.execute("SELECT * FROM completed_uploads ORDER BY completed_at DESC").fetchall()
            return [_row_to_dict(r) for r in rows]
        finally:
            conn.close()

def clear_completed_uploads():

    _init_db()
    with _DB_LOCK:
        conn = _get_conn()
        try:
            conn.execute("DELETE FROM completed_uploads")
            conn.commit()
        finally:
            conn.close()

def delete_completed_upload(upload_id: str):

    _init_db()
    with _DB_LOCK:
        conn = _get_conn()
        try:
            conn.execute("DELETE FROM completed_uploads WHERE id = ?", (upload_id,))
            conn.commit()
        finally:
            conn.close()

