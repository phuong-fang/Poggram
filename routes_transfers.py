import os

from flask import jsonify

import shared
import store
import telegram_client

def register(app):

    @app.route("/api/transfers/interrupted", methods=["GET"])
    def interrupted_transfers_route():
        uploads = []
        for record in store.list_pending_uploads():
            if record["source"] == "sync":
                continue

            with shared.uploads_lock:
                still_active = record["id"] in shared.uploads
            if still_active:
                continue
            exists = os.path.isfile(record["local_path"])
            size_matches = exists and os.path.getsize(record["local_path"]) == record["size_bytes"]

            bytes_done = sum(c["size_bytes"] for c in record["chunks"])
            if record.get("upload_file_id") is not None:
                bytes_done += (record.get("upload_parts_sent") or 0) * (record.get("upload_part_size") or 0)
            uploads.append({
                "id": record["id"],
                "filename": record["filename"],
                "bytes_done": bytes_done,
                "bytes_total": record["size_bytes"],

                "resumable": size_matches,

                "relative_path": record["relative_path"],

                "folder_id": record.get("folder_id"),
            })
        return jsonify({"uploads": uploads})

    @app.route("/api/transfers/completed", methods=["GET"])
    def completed_transfers_route():

        settings = store.load_settings()
        if settings.get("completed_uploads_persistence") != "keep":
            return jsonify({"uploads": []})
        return jsonify({"uploads": store.list_completed_uploads()})

    @app.route("/api/transfers/completed/<upload_id>", methods=["DELETE"])
    def dismiss_completed_upload_route(upload_id):

        store.delete_completed_upload(upload_id)
        return jsonify({"ok": True})

    @app.route("/api/transfers/completed/clear", methods=["POST"])
    def clear_completed_uploads_route():

        store.clear_completed_uploads()
        return jsonify({"ok": True})

    @app.route("/api/uploads/interrupted/<upload_id>/continue", methods=["POST"])
    def continue_interrupted_upload_route(upload_id):
        record = store.find_pending_upload(upload_id)
        if record is None:
            return jsonify({"error": "not found"}), 404

        if record["source"] == "sync":
            return jsonify({"error": "Sync uploads resume automatically on the next sync cycle - use Dismiss to clean up instead."}), 400
        if not os.path.isfile(record["local_path"]) or os.path.getsize(record["local_path"]) != record["size_bytes"]:
            return jsonify({"error": "That file has moved, changed, or no longer exists - can't safely resume it."}), 400

        resume_part_state = None
        if record.get("upload_file_id") is not None:
            resume_part_state = {
                "file_id": record["upload_file_id"],
                "part_size": record["upload_part_size"],
                "parts_sent": record["upload_parts_sent"],
            }

        store.delete_pending_upload(upload_id)
        new_upload_id = shared.start_background_upload(
            record["local_path"], record["filename"], record["folder_id"], record["max_chunk_size"],
            target_file_id=record["target_file_id"], source=record["source"],
            skip_duplicate_check=record["skip_duplicate_check"], force=record["force"],
            relative_path=record["relative_path"], resume_chunks=record["chunks"],
            resume_part_state=resume_part_state,

            cleanup_path=record["local_path"] if record["owns_local_path"] else None,
        )
        return jsonify({"ok": True, "upload_id": new_upload_id})

    @app.route("/api/uploads/interrupted/<upload_id>/cancel", methods=["POST"])
    def cancel_interrupted_upload_route(upload_id):

        record = store.find_pending_upload(upload_id)
        if record is None:
            with shared.uploads_lock:
                had_live_entry = upload_id in shared.uploads
                shared.uploads.pop(upload_id, None)
                shared.upload_retry_info.pop(upload_id, None)
                shared.upload_cancel_tokens.pop(upload_id, None)

            if had_live_entry:
                return jsonify({"ok": True})
            return jsonify({"error": "not found"}), 404

        if record["chunks"]:
            try:
                telegram_client.delete_documents(
                    record["telegram_chat_id"], [c["message_id"] for c in record["chunks"]]
                )
            except Exception as e:
                return jsonify({"error": f"Telegram delete failed: {shared.client_error(e)}"}), 502

        if record["owns_local_path"]:
            try:
                os.remove(record["local_path"])
            except OSError:
                pass
        store.delete_pending_upload(upload_id)
        with shared.uploads_lock:
            shared.uploads.pop(upload_id, None)
            shared.upload_retry_info.pop(upload_id, None)
            shared.upload_cancel_tokens.pop(upload_id, None)
        return jsonify({"ok": True})
