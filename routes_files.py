import os
import tempfile

from flask import jsonify, request

import store
import telegram_client
import shared
import thumbnails

def register(app):
    @app.route("/api/files", methods=["GET"])
    def list_files():
        return jsonify([shared.file_list_record(f)
                        for f in store.load_files() if not f["deleted"]])

    @app.route("/api/files", methods=["POST"])
    def create_file_route():
        folder_id = request.form.get("folder_id") or None
        file_storage = request.files.get("file")
        if not file_storage:
            return jsonify({"ok": False, "error": "No file provided."}), 400
        if folder_id is not None:
            folder = next((f for f in store.load_folders() if f["id"] == folder_id), None)
            if folder is None or folder["deleted"]:
                return jsonify({"ok": False, "error": "Folder not found."}), 400

        settings = store.load_settings()
        max_chunk_size = settings.get("max_chunk_size_bytes") or 1_900_000_000

        tmp_path = shared.take_uploaded_file_path(file_storage)
        filename = file_storage.filename or "file"

        force = request.form.get("force") == "true"
        upload_id = shared.start_background_upload(
            tmp_path, filename, folder_id, max_chunk_size, cleanup_path=tmp_path, force=force
        )
        return jsonify({"upload_id": upload_id}), 202

    @app.route("/api/files/<file_id>/versions", methods=["POST"])
    def upload_new_version_route(file_id):
        file = store.find_file(file_id)
        if file is None:
            return jsonify({"ok": False, "error": "File not found."}), 404
        file_storage = request.files.get("file")
        if not file_storage:
            return jsonify({"ok": False, "error": "No file provided."}), 400
        settings = store.load_settings()
        max_chunk_size = settings.get("max_chunk_size_bytes") or 1_900_000_000

        tmp_path = shared.take_uploaded_file_path(file_storage)
        filename = file_storage.filename or file["name"]
        upload_id = shared.start_background_upload(
            tmp_path, filename, file["folder_id"], max_chunk_size, cleanup_path=tmp_path, target_file_id=file_id
        )
        return jsonify({"upload_id": upload_id}), 202

    @app.route("/api/files/<file_id>/versions", methods=["GET"])
    def list_file_versions_route(file_id):
        file = store.find_file(file_id)
        if file is None:
            return jsonify({"error": "not found"}), 404
        return jsonify({
            "current_version": file["current_version"],
            "versions": [
                {"index": i, "size_bytes": v["size_bytes"], "uploaded_at": v["uploaded_at"]}
                for i, v in enumerate(file["versions"])
            ],
        })

    @app.route("/api/files/<file_id>/versions/<int:version_index>/restore", methods=["POST"])
    def restore_file_version_route(file_id, version_index):
        file, error = store.restore_file_version(file_id, version_index)
        if error:
            status = 404 if error == "File not found." else 400
            return jsonify({"error": error}), status
        shared.mark_app_data_changed()
        return jsonify(file)

    @app.route("/api/files/<file_id>", methods=["PUT"])
    def update_file_route(file_id):
        fields = request.get_json(force=True) or {}
        old_file = store.find_file(file_id) if "name" in fields else None
        old_name = old_file["name"] if old_file else None
        file, error = store.update_file(file_id, fields)
        if error:
            status = 404 if error == "File not found." else 400
            return jsonify({"error": error}), status

        if "name" in fields and old_file and fields["name"] != old_name:
            chat_id = old_file["telegram_chat_id"]
            if old_file.get("meta_message_id"):
                if fields["name"] == old_file.get("original_name"):

                    telegram_client.delete_meta_message(chat_id, old_file["meta_message_id"])
                    store.update_file(file_id, {"meta_message_id": None})
                else:
                    telegram_client.update_meta_message(chat_id, old_file["meta_message_id"], file_id, fields["name"], old_name)
            else:

                meta_id = None
                if old_file.get("chunks"):
                    meta_id = telegram_client.send_meta_message(chat_id, old_file["chunks"][0]["message_id"], file_id, fields["name"])
                if meta_id is not None:
                    store.update_file(file_id, {"meta_message_id": meta_id})
        shared.mark_app_data_changed()
        return jsonify(file)

    @app.route("/api/files/bulk-star", methods=["POST"])
    def bulk_star_route():
        fields = request.get_json(force=True) or {}
        file_ids = fields.get("file_ids", [])
        starred = bool(fields.get("starred", True))
        if not file_ids:
            return jsonify({"error": "No file_ids provided"}), 400
        updated = 0
        for fid in file_ids:
            file, error = store.update_file(fid, {"starred": starred})
            if file:
                updated += 1
        shared.mark_app_data_changed()
        return jsonify({"ok": True, "updated": updated})

    @app.route("/api/files/<file_id>/opened", methods=["POST"])
    def mark_file_opened_route(file_id):
        file = store.mark_file_opened(file_id)
        if file is None:
            return jsonify({"error": "not found"}), 404
        return jsonify(file)

    @app.route("/api/files/<file_id>", methods=["DELETE"])
    def delete_file_route(file_id):
        ok = store.soft_delete_file(file_id)
        if not ok:
            return jsonify({"error": "not found"}), 404
        shared.mark_app_data_changed()
        return jsonify({"ok": True})

    @app.route("/api/files/<file_id>/restore", methods=["POST"])
    def restore_file_route(file_id):
        file, error = store.restore_file(file_id)
        if error:
            return jsonify({"error": error}), 404
        shared.mark_app_data_changed()
        return jsonify(file)

    @app.route("/api/files/<file_id>/permanent", methods=["DELETE"])
    def permanent_delete_file_route(file_id):
        file = store.find_file(file_id)
        if file is None:
            return jsonify({"error": "not found"}), 404
        try:
            message_ids = [c["message_id"] for v in file["versions"] for c in v["chunks"]]
            if file.get("meta_message_id"):
                message_ids.append(file["meta_message_id"])
            telegram_client.delete_documents(file["telegram_chat_id"], message_ids)
        except Exception as e:
            return jsonify({"error": f"Telegram delete failed: {shared.client_error(e)}"}), 502
        store.permanent_delete_file(file_id)
        shared.mark_app_data_changed()
        return jsonify({"ok": True})

    @app.route("/api/files/<file_id>/properties")
    def file_properties_route(file_id):

        file = store.find_file(file_id)
        if file is None:
            return jsonify({"error": "not found"}), 404
        version = store.current_version(file)
        result = {
            "name": file["name"],
            "size_bytes": version["size_bytes"],
            "mime_type": version.get("mime_type"),
            "version_count": len(file["versions"]),
            "date_uploaded": file["date_uploaded"],
            "date_modified": file["date_modified"],
        }
        mime_type = version.get("mime_type") or ""
        if mime_type.startswith("image/") or mime_type.startswith("video/"):
            media = thumbnails.probe_media_info(f"http://{request.host}/api/files/{file_id}/content")
            if media:
                result["media"] = media
        return jsonify(result)
