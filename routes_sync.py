import os

from flask import jsonify, request

import shared
import store
import sync_engine
from sync_engine import _is_under

def _validate_sync_pair_fields(local_path, folder_id, enabled):

    if folder_id is None:
        return "A target Vault folder is required."
    folder = next((f for f in store.load_folders() if f["id"] == folder_id), None)
    if folder is None or folder["deleted"]:
        return "Folder not found."
    if enabled:
        if not local_path or not os.path.isdir(local_path):
            return "That local folder doesn't exist."
    return None

def register(app):
    @app.route("/api/sync/pairs", methods=["GET"])
    def list_sync_pairs_route():
        return jsonify(sync_engine.status())

    @app.route("/api/sync/uploads", methods=["GET"])
    def list_sync_uploads_route():

        with shared.uploads_lock:
            sync_uploads = [
                {**info, "upload_id": uid}
                for uid, info in shared.uploads.items()
                if info.get("source") == "sync"
            ]
        return jsonify(sync_uploads)

    @app.route("/api/sync/uploads/clear-finished", methods=["POST"])
    def clear_sync_uploads_route():

        with shared.uploads_lock:
            to_remove = [
                uid for uid, info in shared.uploads.items()
                if info.get("source") == "sync" and info.get("status") in ("done", "duplicate", "error")
            ]
            for uid in to_remove:
                shared.uploads.pop(uid, None)
                shared.upload_cancel_tokens.pop(uid, None)
                shared.upload_retry_info.pop(uid, None)
        return jsonify({"cleared": len(to_remove)})

    @app.route("/api/sync/pairs", methods=["POST"])
    def create_sync_pair_route():
        fields = request.get_json(force=True) or {}
        local_path = (fields.get("local_path") or "").strip()
        folder_id = fields.get("folder_id")
        paused = bool(fields.get("paused", True))
        exclude_dot_files = bool(fields.get("exclude_dot_files", True))
        reupload_mode = fields.get("reupload_mode", "flag")
        if reupload_mode not in ("flag", "version", "soft_delete", "new_file"):
            return jsonify({"error": "reupload_mode must be flag, version, soft_delete, or new_file"}), 400
        error = _validate_sync_pair_fields(local_path, folder_id, not paused)
        if error:
            return jsonify({"error": error}), 400

        def _create_and_notify():
            pair = store.add_sync_pair(local_path, folder_id, paused=paused, exclude_dot_files=exclude_dot_files, reupload_mode=reupload_mode)
            sync_engine.pair_created(pair)
            return pair

        pair = store.with_sync_pairs_lock(_create_and_notify)
        return jsonify(sync_engine.status()), 201

    @app.route("/api/sync/pairs/<pair_id>", methods=["PUT"])
    def update_sync_pair_route(pair_id):
        existing = store.find_sync_pair(pair_id)
        if existing is None:
            return jsonify({"error": "not found"}), 404
        fields = request.get_json(force=True) or {}
        updates = {}
        if "local_path" in fields:
            updates["local_path"] = (fields["local_path"] or "").strip()
        if "folder_id" in fields:
            updates["folder_id"] = fields["folder_id"]
        if "paused" in fields:
            updates["paused"] = bool(fields["paused"])
        if "exclude_dot_files" in fields:
            updates["exclude_dot_files"] = bool(fields["exclude_dot_files"])
        if "reupload_mode" in fields:
            if fields["reupload_mode"] not in ("flag", "version", "soft_delete", "new_file"):
                return jsonify({"error": "reupload_mode must be flag, version, soft_delete, or new_file"}), 400
            updates["reupload_mode"] = fields["reupload_mode"]
        effective_local_path = updates.get("local_path", existing["local_path"])
        effective_folder_id = updates.get("folder_id", existing["folder_id"])
        effective_paused = updates.get("paused", existing.get("paused", True))
        error = _validate_sync_pair_fields(effective_local_path, effective_folder_id, not effective_paused)
        if error:
            return jsonify({"error": error}), 400

        def _update_and_notify():
            pair = store.update_sync_pair(pair_id, updates)
            sync_engine.pair_updated(pair)
            return pair

        pair = store.with_sync_pairs_lock(_update_and_notify)
        return jsonify(sync_engine.status())

    @app.route("/api/sync/pairs/<pair_id>", methods=["DELETE"])
    def delete_sync_pair_route(pair_id):

        pair = store.find_sync_pair(pair_id)

        def _delete_and_notify():
            ok = store.delete_sync_pair(pair_id)
            sync_engine.pair_deleted(pair_id)
            return ok

        ok = store.with_sync_pairs_lock(_delete_and_notify)
        if not ok:
            return jsonify({"error": "not found"}), 404

        store.clear_sync_pair_state(pair_id, pair.get("local_path") if pair else None)

        if pair and pair.get("local_path"):
            local_root = pair["local_path"]
            with shared.uploads_lock:
                to_remove = []
                to_forget_cancel = []
                for uid, info in shared.uploads.items():
                    if info.get("source") != "sync":
                        continue
                    retry_info = shared.upload_retry_info.get(uid, {})
                    file_path = retry_info.get("file_path", "")
                    if not file_path or not _is_under(file_path, local_root):
                        continue
                    if info.get("status") in ("uploading", "queued"):
                        to_forget_cancel.append(uid)
                    else:
                        to_remove.append(uid)
                for uid in to_remove:
                    shared.uploads.pop(uid, None)
                    shared.upload_cancel_tokens.pop(uid, None)
                    shared.upload_retry_info.pop(uid, None)
                for uid in to_forget_cancel:
                    token = shared.upload_cancel_tokens.get(uid)
                    if token:
                        token.cancel(forget=True)
        return jsonify(sync_engine.status())
