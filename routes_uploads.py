import os
import logging
import tempfile
import uuid

from flask import jsonify, request

import store
import telegram_client
import shared

logger = logging.getLogger(__name__)

def register(app):
    @app.route("/api/folders/upload-tree", methods=["POST"])
    def upload_folder_tree_route():

        fields = request.get_json(force=True) or {}
        root_path = fields.get("path")
        target_folder_id = fields.get("folder_id") or None
        if not root_path or not os.path.isdir(root_path):
            return jsonify({"error": "That path doesn't point to an existing folder."}), 400
        if target_folder_id is not None:
            parent = next((f for f in store.load_folders() if f["id"] == target_folder_id), None)
            if parent is None or parent["deleted"]:
                logger.warning(f"Folder upload: target_folder_id={target_folder_id} not found or deleted, falling back to root")
                target_folder_id = None

        root_name = os.path.basename(root_path.rstrip("\\/")) or root_path
        root_folder, error = store.get_or_create_folder(root_name, target_folder_id)
        if error:
            return jsonify({"error": error}), 400

        path_to_folder_id = {root_path: root_folder["id"]}
        pending_uploads = []
        for dirpath, dirnames, filenames in os.walk(root_path):
            parent_folder_id = path_to_folder_id[dirpath]
            for dirname in dirnames:
                sub_folder, sub_error = store.get_or_create_folder(dirname, parent_folder_id)
                if sub_error:
                    logger.warning(f"Folder tree upload: failed to create subfolder '{dirname}' under {parent_folder_id}: {sub_error}")
                    continue
                path_to_folder_id[os.path.join(dirpath, dirname)] = sub_folder["id"]
            for filename in filenames:
                file_path = os.path.join(dirpath, filename)

                rel = os.path.relpath(file_path, root_path).replace(os.sep, "/")

                try:
                    size_bytes = os.path.getsize(file_path)
                except OSError:
                    size_bytes = None
                pending_uploads.append({
                    "id": str(uuid.uuid4()), "file_path": file_path, "filename": filename,
                    "folder_id": parent_folder_id, "relative_path": rel, "size_bytes": size_bytes,
                })

        store.save_queued_uploads(pending_uploads)

        return jsonify({"ok": True, "root_folder": root_folder, "pending_uploads": pending_uploads})

    @app.route("/api/uploads/queued", methods=["GET"])
    def list_queued_uploads_route():

        return jsonify({"uploads": store.list_queued_uploads()})

    @app.route("/api/uploads/queued/<queued_id>/dismiss", methods=["POST"])
    def dismiss_queued_upload_route(queued_id):
        store.delete_queued_upload(queued_id)
        return jsonify({"ok": True})

    @app.route("/api/uploads/queued/stage", methods=["POST"])
    def stage_queued_upload_route():

        folder_id = request.form.get("folder_id") or None
        relative_path = request.form.get("relative_path") or None
        file_storage = request.files.get("file")
        if not file_storage:
            return jsonify({"error": "No file provided."}), 400
        if folder_id is not None:
            parent = next((f for f in store.load_folders() if f["id"] == folder_id), None)
            if parent is None or parent["deleted"]:
                logger.warning(f"Stage queued upload: folder_id={folder_id} not found or deleted, falling back to root")
                folder_id = None

        tmp_path = shared.take_uploaded_file_path(file_storage, prefix="tgv_dropped_")
        filename = file_storage.filename or "file"

        pending = {
            "id": str(uuid.uuid4()), "file_path": tmp_path, "filename": filename,
            "folder_id": folder_id, "relative_path": relative_path, "owns_local_path": True,
        }
        try:
            store.save_queued_uploads([pending])
        except Exception:

            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise
        return jsonify({"ok": True, **pending})

    @app.route("/api/uploads/start-from-path", methods=["POST"])
    def start_upload_from_path_route():

        fields = request.get_json(force=True) or {}
        file_path = fields.get("file_path")
        filename = fields.get("filename")
        folder_id = fields.get("folder_id") or None
        queued_id = fields.get("queued_id")
        if not file_path or not filename or not os.path.isfile(file_path):
            return jsonify({"error": "That file is no longer there - it may have moved or been deleted."}), 400
        if folder_id is not None:
            parent = next((f for f in store.load_folders() if f["id"] == folder_id), None)
            if parent is None or parent["deleted"]:
                logger.warning(f"Start upload from path: folder_id={folder_id} not found or deleted, falling back to root")
                folder_id = None

        cleanup_path = None
        relative_path = None
        if queued_id:
            queued = store.find_queued_upload(queued_id)
            if queued and queued["owns_local_path"]:
                cleanup_path = file_path

            if queued:
                relative_path = queued.get("relative_path")

        skip_duplicate_check = fields.get("skip_duplicate_check", False)

        settings = store.load_settings()
        max_chunk_size = settings.get("max_chunk_size_bytes") or 1_900_000_000

        upload_id = shared.start_background_upload(
            file_path, filename, folder_id, max_chunk_size, cleanup_path=cleanup_path,
            skip_duplicate_check=bool(skip_duplicate_check), relative_path=relative_path,
            force=bool(fields.get("force")), target_file_id=fields.get("target_file_id"),
            queued_id=queued_id,
        )
        return jsonify({"ok": True, "upload_id": upload_id})

    @app.route("/api/wipe/versioned", methods=["POST"])
    def wipe_versioned_route():
        messages_by_chat, files_affected, bytes_freed = store.versioned_data_summary()
        try:
            for chat_id, message_ids in messages_by_chat.items():
                telegram_client.delete_documents(chat_id, message_ids)
        except Exception as e:
            return jsonify({"error": f"Telegram delete failed: {shared.client_error(e)}"}), 502
        store.apply_versioned_wipe()
        shared.mark_app_data_changed()
        return jsonify({"files_affected": files_affected, "bytes_freed": bytes_freed})

    @app.route("/api/wipe/all", methods=["POST"])
    def wipe_all_route():
        messages_by_chat, file_count, bytes_freed = store.everything_summary()
        try:
            for chat_id, message_ids in messages_by_chat.items():
                telegram_client.delete_documents(chat_id, message_ids)
        except Exception as e:
            return jsonify({"error": f"Telegram delete failed: {shared.client_error(e)}"}), 502
        store.apply_everything_wipe()
        shared.mark_app_data_changed()
        return jsonify({"files_deleted": file_count, "bytes_freed": bytes_freed})

    @app.route("/api/uploads/<upload_id>", methods=["GET"])
    def get_upload_status(upload_id):
        with shared.uploads_lock:
            info = shared.uploads.get(upload_id)

            if info and info["status"] in ("done", "error", "duplicate"):
                shared.uploads.pop(upload_id, None)
        if info is None:
            return jsonify({"error": "not found"}), 404
        return jsonify(info)

    @app.route("/api/uploads/<upload_id>/cancel", methods=["POST"])
    def cancel_upload_route(upload_id):
        with shared.uploads_lock:
            info = shared.uploads.get(upload_id)
            token = shared.upload_cancel_tokens.get(upload_id)
        if info is None:
            return jsonify({"error": "not found"}), 404

        if info["status"] not in ("uploading", "queued"):
            return jsonify({"error": f"Upload is already {info['status']}"}), 400

        forget = bool((request.get_json(silent=True) or {}).get("forget"))
        if token:
            token.cancel(forget=forget)
        return jsonify({"status": "cancelling"})

    @app.route("/api/uploads/<upload_id>/continue", methods=["POST"])
    def continue_upload_route(upload_id):

        with shared.uploads_lock:
            info = shared.uploads.get(upload_id)
            retry = shared.upload_retry_info.get(upload_id)
        if info is None:
            return jsonify({"error": "not found"}), 404
        if info["status"] != "cancelled":
            return jsonify({"error": f"Upload is {info['status']}, not paused."}), 400
        if not retry:
            return jsonify({"error": "This upload can't be continued from here."}), 400
        if not os.path.isfile(retry["file_path"]):
            return jsonify({"error": "The original file is no longer at its previous location."}), 400

        resume_chunks = None
        resume_part_state = None
        if retry.get("size_bytes") is not None and os.path.getsize(retry["file_path"]) == retry["size_bytes"]:
            resume_chunks = retry.get("resume_chunks") or None
            resume_part_state = retry.get("resume_part_state")

        store.delete_pending_upload(upload_id)

        new_upload_id = shared.start_background_upload(
            retry["file_path"], retry["filename"], retry["folder_id"], retry["max_chunk_size"],
            cleanup_path=retry.get("cleanup_path"),
            target_file_id=retry.get("target_file_id"),
            skip_duplicate_check=retry.get("skip_duplicate_check", False),
            force=retry.get("force", False),
            resume_chunks=resume_chunks,
            resume_part_state=resume_part_state,
        )
        with shared.uploads_lock:
            shared.upload_retry_info.pop(upload_id, None)

            shared.uploads.pop(upload_id, None)
        return jsonify({"upload_id": new_upload_id}), 202
