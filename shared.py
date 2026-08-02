import logging
import math
import mimetypes
import os
import tempfile
import threading
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import store
import sync_engine
import telegram_client
import thumbnails

logger = logging.getLogger(__name__)

_thumbnail_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="thumb-gen-")

uploads = {}
uploads_lock = threading.Lock()

upload_cancel_tokens = {}

upload_retry_info = {}

hashes_in_progress = set()
hashes_in_progress_lock = threading.Lock()

upload_transfer_slot = threading.Semaphore(1)

chunk_locks = OrderedDict()
chunk_locks_guard = threading.Lock()
CHUNK_LOCKS_MAX = 1000

def _chunk_lock_entry(key):

    with chunk_locks_guard:
        entry = chunk_locks.get(key)
        if entry is None:
            if len(chunk_locks) >= CHUNK_LOCKS_MAX:

                for k, v in chunk_locks.items():
                    if v["count"] == 0:
                        chunk_locks.pop(k)
                        break
                else:

                    chunk_locks.popitem(last=False)
            entry = {"lock": threading.Lock(), "count": 0}
            chunk_locks[key] = entry
        else:
            chunk_locks.move_to_end(key)
        entry["count"] += 1
        return entry

class _ChunkLock:

    def __init__(self, file_id, version_index, chunk_index):
        self.key = (file_id, version_index, chunk_index)
        self.entry = None

    def __enter__(self):
        self.entry = _chunk_lock_entry(self.key)
        self.entry["lock"].acquire()
        return self.entry["lock"]

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.entry["lock"].release()
        with chunk_locks_guard:
            self.entry["count"] -= 1

def chunk_lock(file_id, version_index, chunk_index):

    return _ChunkLock(file_id, version_index, chunk_index)

_app_data_dirty = None
_app_data_dirty_lock = threading.Lock()

APP_DATA_SNAPSHOT_RETENTION_DAYS = 90

def _build_and_upload_app_data_snapshot(on_build_progress=None, on_upload_progress=None, on_stage=None):

    _clear_app_data_dirty()
    try:
        return _do_build_and_upload_app_data_snapshot(
            on_build_progress=on_build_progress, on_upload_progress=on_upload_progress, on_stage=on_stage,
        )
    except Exception:
        mark_app_data_changed()
        raise

def _do_build_and_upload_app_data_snapshot(on_build_progress=None, on_upload_progress=None, on_stage=None):
    if on_stage:
        on_stage("building")

    include_thumbnails = bool(store.load_settings().get("app_data_backup_include_thumbnails"))
    snapshot_bytes = store.build_app_data_snapshot(
        on_progress=on_build_progress, include_thumbnails=include_thumbnails,
    )
    filename = f"vault-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.tar.xz"
    if on_stage:
        on_stage("uploading")
    message_id = telegram_client.upload_app_data_snapshot(
        snapshot_bytes, filename, on_progress=on_upload_progress,
    )
    store.save_settings_fields({"app_data_backup_last_known_message_id": message_id})
    if on_stage:
        on_stage("pruning")
    cutoff = datetime.now(timezone.utc) - timedelta(days=APP_DATA_SNAPSHOT_RETENTION_DAYS)
    stale_ids = [
        s["message_id"] for s in telegram_client.list_app_data_snapshots()
        if datetime.fromisoformat(s["date"]) < cutoff
    ]
    telegram_client.delete_app_data_snapshots(stale_ids)

def _run_app_data_snapshot():

    try:
        if not store.load_settings().get("app_data_backup_enabled"):
            return
        status = telegram_client.status()
        if not status.get("connected") or not status.get("archive_chat_id"):
            return
        _build_and_upload_app_data_snapshot()
    except Exception:
        logger.exception("On-close app-data snapshot failed")

def _app_data_is_dirty():

    global _app_data_dirty
    with _app_data_dirty_lock:
        if _app_data_dirty is None:
            _app_data_dirty = bool(store.load_settings().get("app_data_backup_pending_changes"))
        return _app_data_dirty

def mark_app_data_changed():

    global _app_data_dirty
    if _app_data_is_dirty():
        return
    with _app_data_dirty_lock:
        if _app_data_dirty:
            return
        _app_data_dirty = True
    store.save_settings_fields({"app_data_backup_pending_changes": True})

def _clear_app_data_dirty():
    global _app_data_dirty
    with _app_data_dirty_lock:
        _app_data_dirty = False
    store.save_settings_fields({"app_data_backup_pending_changes": False})

restore_status = {"status": "idle"}
restore_status_lock = threading.Lock()

backup_status = {"status": "idle"}
backup_status_lock = threading.Lock()

def run_app_data_backup(on_finished=None):

    with backup_status_lock:
        backup_status.clear()
        backup_status.update({
            "status": "building", "bytes_done": 0, "bytes_total": 0,
            "files_done": 0, "files_total": 0, "error": None,
        })

    def _on_stage(stage):
        with backup_status_lock:
            backup_status["status"] = stage

    def _on_build_progress(done, total):
        with backup_status_lock:
            backup_status["files_done"] = done
            backup_status["files_total"] = total

    def _on_upload_progress(sent, total):
        with backup_status_lock:
            backup_status["bytes_done"] = sent
            backup_status["bytes_total"] = total

    def _run():
        try:
            _build_and_upload_app_data_snapshot(
                on_build_progress=_on_build_progress,
                on_upload_progress=_on_upload_progress,
                on_stage=_on_stage,
            )
            with backup_status_lock:
                backup_status["status"] = "done"
        except Exception as e:
            logger.exception("Manual app-data snapshot failed")
            with backup_status_lock:
                backup_status["status"] = "error"
                backup_status["error"] = str(e) or type(e).__name__
        finally:
            if on_finished:
                try:
                    on_finished()
                except Exception:
                    logger.exception("app-data backup on_finished callback failed")

    threading.Thread(target=_run, daemon=True).start()

def run_app_data_restore(message_id, on_finished=None):

    with restore_status_lock:
        restore_status.clear()
        restore_status.update({
            "status": "downloading", "bytes_done": 0, "bytes_total": 0,
            "thumbnails_done": 0, "thumbnails_total": 0, "error": None,
        })

    def _on_download_progress(received, total):
        with restore_status_lock:
            restore_status["bytes_done"] = received
            restore_status["bytes_total"] = total

    def _on_restore_progress(done, total):
        with restore_status_lock:
            restore_status["status"] = "restoring"
            restore_status["thumbnails_done"] = done
            restore_status["thumbnails_total"] = total

    def _run():
        try:
            sync_engine.shutdown()
            try:
                snapshot_bytes = telegram_client.download_app_data_snapshot(message_id, on_progress=_on_download_progress)
                with restore_status_lock:
                    restore_status["status"] = "restoring"
                store.restore_app_data_snapshot(snapshot_bytes, on_progress=_on_restore_progress)
                store.save_settings_fields({"app_data_backup_last_known_message_id": message_id})
                with restore_status_lock:
                    restore_status["status"] = "done"
            finally:
                sync_engine.init(start_background_upload)
        except Exception as e:
            logger.exception(f"App-data restore failed: {e}")
            with restore_status_lock:
                restore_status["status"] = "error"
                restore_status["error"] = str(e) or type(e).__name__
        finally:
            if on_finished:
                on_finished()

    threading.Thread(target=_run, daemon=True).start()

def snapshot_now_blocking():

    if not _app_data_is_dirty():
        logger.info("App-data backup: nothing changed since the last snapshot, skipping on-close backup")
        return
    _run_app_data_snapshot()

window = None

def start_background_upload(
    file_path, filename, folder_id, max_chunk_size, cleanup_path=None, on_done=None, target_file_id=None,
    force=False, skip_duplicate_check=False, source="user", relative_path=None, resume_chunks=None,
    resume_part_state=None, queued_id=None, on_duplicate=None,
):

    size_bytes = os.path.getsize(file_path)
    chunks_total = math.ceil(size_bytes / max_chunk_size) if size_bytes > max_chunk_size else 1
    upload_id = uuid.uuid4().hex[:8]

    cancel_token = telegram_client.CancelToken()

    initial_bytes_done = 0
    if resume_chunks:
        initial_bytes_done += sum(c["size_bytes"] for c in resume_chunks)
    if resume_part_state:
        initial_bytes_done += (resume_part_state.get("parts_sent") or 0) * (resume_part_state.get("part_size") or 0)
    initial_chunks_done = len(resume_chunks) if resume_chunks else 0
    with uploads_lock:
        uploads[upload_id] = {
            "status": "uploading", "chunks_done": initial_chunks_done, "chunks_total": chunks_total,
            "bytes_done": initial_bytes_done, "bytes_total": size_bytes, "file": None, "error": None,
            "source": source, "filename": filename, "relative_path": relative_path,

            "folder_id": folder_id,
        }
        upload_cancel_tokens[upload_id] = cancel_token

        upload_retry_info[upload_id] = {
            "file_path": file_path, "filename": filename, "folder_id": folder_id,
            "max_chunk_size": max_chunk_size, "cleanup_path": cleanup_path,
            "target_file_id": target_file_id, "size_bytes": size_bytes,

            "skip_duplicate_check": skip_duplicate_check, "force": force,

            "resume_chunks": list(resume_chunks) if resume_chunks else [],
            "resume_part_state": resume_part_state,
        }

    def _on_progress(chunks_done, chunks_total_actual, bytes_done):
        with uploads_lock:
            uploads[upload_id].update({
                "chunks_done": chunks_done, "chunks_total": chunks_total_actual, "bytes_done": bytes_done,
            })

    def _run():

        outcome = None
        reserved_hash = False

        persist_pending = False

        pending_chat_id = None
        try:
            content_hash = telegram_client.compute_content_hash(file_path)

            if cancel_token is not None and cancel_token.is_cancelled():
                raise telegram_client.UploadCancelled()
            if target_file_id is None and not force and not skip_duplicate_check:
                with hashes_in_progress_lock:
                    already_in_progress = content_hash in hashes_in_progress
                    if not already_in_progress:
                        hashes_in_progress.add(content_hash)
                        reserved_hash = True
                if already_in_progress:

                    with uploads_lock:
                        uploads[upload_id].update({"status": "duplicate", "duplicate_file": None})

                    if on_duplicate:
                        try:
                            on_duplicate(None)
                        except Exception:
                            logger.exception(f"Upload {upload_id}: on_duplicate callback failed")
                    return
                duplicate = store.find_duplicate_by_hash(content_hash)
                if duplicate is not None:
                    with uploads_lock:
                        uploads[upload_id].update({
                            "status": "duplicate",
                            "duplicate_file": {
                                "id": duplicate["id"], "name": duplicate["name"], "folder_id": duplicate["folder_id"],
                            },
                        })

                    if on_duplicate:
                        try:
                            on_duplicate(duplicate)
                        except Exception:
                            logger.exception(f"Upload {upload_id}: on_duplicate callback failed")
                    return

            mime_type, _ = mimetypes.guess_type(filename)
            thumb_bytes = None
            if mime_type:

                thumb_future = None
                if mime_type.startswith("image/"):
                    thumb_future = _thumbnail_executor.submit(thumbnails.generate_image_thumbnail, file_path, fmt="jpeg")
                elif mime_type.startswith("video/"):
                    thumb_future = _thumbnail_executor.submit(thumbnails.generate_video_thumbnail, file_path, fmt="jpeg")

            reply_to = None
            if mime_type and (mime_type.startswith("image/") or mime_type.startswith("video/")):
                try:
                    reply_to = telegram_client.find_or_create_media_topic()
                except Exception:
                    reply_to = None

            if not upload_transfer_slot.acquire(timeout=0.5):
                with uploads_lock:
                    uploads[upload_id]["status"] = "queued"
                while not upload_transfer_slot.acquire(timeout=0.5):
                    if cancel_token is not None and cancel_token.is_cancelled():
                        raise telegram_client.UploadCancelled()
            try:
                with uploads_lock:
                    uploads[upload_id]["status"] = "uploading"

                thumb_bytes = thumb_future.result() if thumb_future else None

                upload_settings = store.load_settings()
                upload_workers = int(upload_settings.get("upload_parallel_workers") or 8)
                upload_part_kb = int(upload_settings.get("upload_part_size_kb") or 0)

                priority = "background" if source == "sync" else "foreground"

                try:
                    pending_chat_id = telegram_client.require_archive_chat()
                    store.save_pending_upload(upload_id, {
                        "local_path": file_path, "filename": filename, "folder_id": folder_id,
                        "target_file_id": target_file_id, "source": source, "size_bytes": size_bytes,
                        "max_chunk_size": max_chunk_size, "telegram_chat_id": pending_chat_id,
                        "chunks": resume_chunks or [], "skip_duplicate_check": skip_duplicate_check,
                        "force": force, "relative_path": relative_path,
                        "owns_local_path": cleanup_path is not None,
                    })
                    persist_pending = True

                    if queued_id:
                        try:
                            store.delete_queued_upload_row_only(queued_id)
                        except Exception:
                            logger.exception(f"Upload {upload_id}: failed to clear queued row {queued_id}")
                except Exception:
                    logger.exception(f"Upload {upload_id}: failed to persist crash-recovery record")

                def _on_chunk_done(chunks_so_far):
                    if persist_pending:
                        store.update_pending_upload_chunks(upload_id, chunks_so_far)

                        store.update_pending_upload_part_state(upload_id, None, None, 0)

                    with uploads_lock:
                        if upload_id in upload_retry_info:
                            upload_retry_info[upload_id]["resume_chunks"] = list(chunks_so_far)
                            upload_retry_info[upload_id]["resume_part_state"] = None

                def _on_part_done(file_id, part_size, parts_sent):
                    if persist_pending:
                        store.update_pending_upload_part_state(upload_id, file_id, part_size, parts_sent)
                    with uploads_lock:
                        if upload_id in upload_retry_info:
                            upload_retry_info[upload_id]["resume_part_state"] = {
                                "file_id": file_id, "part_size": part_size, "parts_sent": parts_sent,
                            }

                if upload_workers > 1:
                    chat_id, chunks = telegram_client.upload_file_parallel(
                        file_path, filename, max_chunk_size, on_progress=_on_progress, cancel_token=cancel_token,
                        content_hash=content_hash, thumb_bytes=thumb_bytes, reply_to=reply_to,
                        num_workers=upload_workers, part_size_kb=upload_part_kb, priority=priority,
                        on_chunk_done=_on_chunk_done, resume_chunks=resume_chunks,
                        resume_part_state=resume_part_state, on_part_done=_on_part_done,
                    )
                else:
                    chat_id, chunks = telegram_client.upload_file(
                        file_path, filename, max_chunk_size, on_progress=_on_progress, cancel_token=cancel_token,
                        content_hash=content_hash, thumb_bytes=thumb_bytes, reply_to=reply_to, priority=priority,
                        on_chunk_done=_on_chunk_done, resume_chunks=resume_chunks,
                    )
            finally:
                upload_transfer_slot.release()
            if target_file_id is not None:
                record, error = store.add_file_version(target_file_id, {
                    "chunks": chunks,
                    "size_bytes": size_bytes,
                    "mime_type": mime_type,
                    "content_hash": content_hash,
                    "has_thumbnail": bool(thumb_bytes),
                })
                if error:
                    raise RuntimeError(error)
                version_index = record["current_version"]
            else:
                record = store.create_file({
                    "name": filename,
                    "folder_id": folder_id,
                    "size_bytes": size_bytes,
                    "mime_type": mime_type,
                    "telegram_chat_id": chat_id,
                    "chunks": chunks,
                    "source": source,
                    "content_hash": content_hash,
                    "has_thumbnail": bool(thumb_bytes),
                })
                version_index = 0
            if thumb_bytes:

                settings = store.load_settings()
                enc = {
                    "fmt": settings.get("thumbnail_format") or "jpeg",
                    "quality": settings.get("thumbnail_quality"),
                    "subsampling": settings.get("thumbnail_chroma_subsampling"),
                }
                cache_bytes = None
                if mime_type.startswith("image/"):
                    cache_bytes = thumbnails.generate_image_thumbnail(file_path, **enc)
                elif mime_type.startswith("video/"):
                    cache_bytes = thumbnails.generate_video_thumbnail(file_path, **enc)
                cache_fmt = enc["fmt"] if cache_bytes else "jpeg"
                store.write_thumbnail_cache(
                    record["id"], version_index, cache_bytes or thumb_bytes, store.thumbnail_ext_for_format(cache_fmt)
                )
            with uploads_lock:
                uploads[upload_id].update({"status": "done", "file": record})
            outcome = "done"

            try:
                settings = store.load_settings()

                if settings.get("completed_uploads_persistence") == "keep" and source != "sync":
                    with uploads_lock:
                        upload_info = uploads.get(upload_id, {})
                    store.save_completed_upload({
                        "id": upload_id,
                        "filename": upload_info.get("filename", filename),
                        "folder_id": folder_id,
                        "relative_path": upload_info.get("relative_path", relative_path),
                        "bytes_done": upload_info.get("bytes_done", size_bytes),
                        "bytes_total": upload_info.get("bytes_total", size_bytes),
                        "kind": "upload",
                    })
            except Exception:
                logger.exception(f"Upload {upload_id}: failed to persist the completed-upload row (upload itself succeeded)")
        except telegram_client.UploadCancelled:
            with uploads_lock:
                uploads[upload_id].update({"status": "cancelled"})
            outcome = "cancelled"
            return
        except Exception as e:

            logger.exception(f"Upload {upload_id} failed: {e}")
            with uploads_lock:
                uploads[upload_id].update({"status": "error", "error": str(e) or type(e).__name__})
            outcome = "error"
            return
        finally:
            if reserved_hash:
                with hashes_in_progress_lock:
                    hashes_in_progress.discard(content_hash)
            with uploads_lock:

                upload_info = uploads.get(upload_id)
                current_status = outcome or (upload_info["status"] if upload_info else "error")
                upload_cancel_tokens.pop(upload_id, None)
                retry_info = upload_retry_info.get(upload_id)

            forget = cancel_token.should_forget()

            if cleanup_path and (current_status != "cancelled" or forget):
                try:
                    os.remove(cleanup_path)
                except OSError:
                    pass

            if forget and retry_info and retry_info.get("resume_chunks") and pending_chat_id:
                try:
                    telegram_client.delete_documents(
                        pending_chat_id, [c["message_id"] for c in retry_info["resume_chunks"]]
                    )
                except Exception:
                    logger.exception(f"Upload {upload_id}: failed to delete orphaned chunks on forget-cancel")

            if persist_pending and (current_status != "cancelled" or forget):
                store.delete_pending_upload(upload_id)
            if forget:
                with uploads_lock:
                    upload_retry_info.pop(upload_id, None)

                    uploads.pop(upload_id, None)

        if on_done:
            try:
                on_done(record)
            except Exception:
                logger.exception(f"Upload {upload_id}: on_done callback failed")

        mark_app_data_changed()

    threading.Thread(target=_run, daemon=True).start()
    return upload_id

_COMMON_VIDEO_PLAYER_PATHS = [
    r"C:\Program Files\MPC-HC\mpc-hc64.exe",
    r"C:\Program Files\MPC-HC\mpc-hc.exe",
    r"C:\Program Files (x86)\MPC-HC\mpc-hc64.exe",
    r"C:\Program Files (x86)\MPC-HC\mpc-hc.exe",
    r"C:\Program Files\K-Lite Codec Pack\MPC-HC64\mpc-hc64.exe",
    r"C:\Program Files (x86)\K-Lite Codec Pack\MPC-HC\mpc-hc.exe",
]

UPLOAD_TEMP_PREFIX = "tgv_upload_"

def new_upload_temp_file(prefix=UPLOAD_TEMP_PREFIX):

    os.makedirs(store.DATA_DIR, exist_ok=True)
    fd, path = tempfile.mkstemp(prefix=prefix, dir=store.DATA_DIR)
    os.close(fd)
    return path, open(path, "rb+")

def _claim_staged_upload(path):

    try:
        from flask import has_request_context, request

        if not has_request_context():
            return
        paths = getattr(request, "vault_upload_paths", None)
        if not paths:
            return

        for entry in list(paths):
            if entry[0] == path:
                paths.remove(entry)
    except Exception:
        logger.exception("Upload staging: could not mark a staged file as claimed")

def take_uploaded_file_path(file_storage, prefix=UPLOAD_TEMP_PREFIX):

    stream = getattr(file_storage, "stream", None)
    existing = getattr(stream, "name", None)
    ours = (
        isinstance(existing, str)
        and os.path.dirname(os.path.abspath(existing)) == os.path.abspath(store.DATA_DIR)
        and os.path.basename(existing).startswith(UPLOAD_TEMP_PREFIX)
    )
    if ours:
        try:

            stream.flush()
            os.fsync(stream.fileno())
            stream.close()
        except Exception:
            logger.exception("Upload staging: could not finalise the staged file, falling back to a copy")
        else:
            _claim_staged_upload(existing)
            if os.path.basename(existing).startswith(prefix):
                return existing
            renamed = os.path.join(
                os.path.dirname(existing),
                prefix + os.path.basename(existing)[len(UPLOAD_TEMP_PREFIX):],
            )
            try:
                os.replace(existing, renamed)
                return renamed
            except OSError:

                logger.exception("Upload staging: rename failed, keeping the original name")
                return existing
    path, handle = new_upload_temp_file(prefix)
    handle.close()
    file_storage.save(path)
    _claim_staged_upload(path)
    return path

def detect_video_player():
    for path in _COMMON_VIDEO_PLAYER_PATHS:
        if os.path.isfile(path):
            return path
    return None
