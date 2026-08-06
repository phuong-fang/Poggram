import os

from flask import jsonify, request

import shared
import store
import telegram_client

def register(app):
    @app.route("/api/folders", methods=["GET"])
    def list_folders():
        return jsonify([f for f in store.load_folders() if not f["deleted"]])

    @app.route("/api/folders", methods=["POST"])
    def create_folder_route():

        fields = request.get_json(force=True) or {}
        if fields.get("reuse_if_exists"):
            folder, error = store.get_or_create_folder(fields.get("name"), fields.get("parent_id"))
        else:
            folder, error = store.create_folder(fields.get("name"), fields.get("parent_id"))
        if error:
            return jsonify({"error": error}), 400
        shared.mark_app_data_changed()
        return jsonify(folder), 201

    @app.route("/api/folders/<folder_id>", methods=["PUT"])
    def update_folder_route(folder_id):
        fields = request.get_json(force=True) or {}
        folder, error = store.update_folder(folder_id, fields)
        if error:
            status = 404 if error == "Folder not found." else 400
            return jsonify({"error": error}), status
        shared.mark_app_data_changed()
        return jsonify(folder)

    @app.route("/api/folders/<folder_id>", methods=["DELETE"])
    def delete_folder_route(folder_id):
        ok = store.soft_delete_folder(folder_id)
        if not ok:
            return jsonify({"error": "not found"}), 404
        shared.mark_app_data_changed()
        return jsonify({"ok": True})

    @app.route("/api/folders/<folder_id>/restore", methods=["POST"])
    def restore_folder_route(folder_id):
        result, error = store.restore_folder(folder_id)
        if error:
            return jsonify({"error": error}), 404
        shared.mark_app_data_changed()
        return jsonify(result)

    @app.route("/api/folders/<folder_id>/properties")
    def folder_properties_route(folder_id):
        folder = next((f for f in store.load_folders() if f["id"] == folder_id), None)
        if folder is None:
            return jsonify({"error": "not found"}), 404
        summary = store.folder_summary(folder_id)
        return jsonify({
            "name": folder["name"],
            "date_created": folder["date_created"],
            **summary,
        })

    @app.route("/api/folders/<folder_id>/permanent", methods=["DELETE"])
    def permanent_delete_folder_route(folder_id):

        descendant_ids = store.descendant_folder_ids(folder_id)
        all_folder_ids = {folder_id} | descendant_ids
        files = store.load_files()
        messages_by_chat = {}
        for f in files:
            if f["folder_id"] in all_folder_ids:
                chat_id = f.get("telegram_chat_id")
                for v in f["versions"]:
                    messages_by_chat.setdefault(chat_id, []).extend(c["message_id"] for c in v["chunks"])
                if f.get("meta_message_id"):
                    messages_by_chat.setdefault(chat_id, []).append(f["meta_message_id"])
        for chat_id, message_ids in messages_by_chat.items():
            try:
                telegram_client.delete_documents(chat_id, message_ids)
            except Exception as e:
                return jsonify({"error": f"Telegram delete failed: {e}"}), 502
        ok, error = store.permanent_delete_folder(folder_id)
        if not ok:
            status = 404 if error == "Folder not found." else 400
            return jsonify({"error": error}), status
        shared.mark_app_data_changed()
        return jsonify({"ok": True})

    @app.route("/api/trash", methods=["GET"])
    def get_trash():
        folders = store.load_folders()
        files = store.load_files()
        return jsonify({
            "folders": [f for f in folders if f["deleted"]],
            "files": [shared.file_list_record(f) for f in files if f["deleted"]],
        })

    @app.route("/api/stats", methods=["GET"])
    def get_stats():

        return jsonify(store.file_stats())

    @app.route("/api/cache/summary", methods=["GET"])
    def cache_summary_route():
        return jsonify({"bytes": store.cache_disk_usage()})

    @app.route("/api/cache/clear", methods=["POST"])
    def cache_clear_route():

        return jsonify({"bytes_freed": store.clear_cache()})

    @app.route("/api/pick-folder", methods=["POST"])
    def pick_folder_route():

        if shared.window is None:
            return jsonify({"path": None})
        import webview
        folder_dialog = getattr(webview, "FOLDER_DIALOG", None)
        if folder_dialog is None:
            folder_dialog = webview.FileDialog.FOLDER
        result = shared.window.create_file_dialog(folder_dialog)
        path = result[0] if result else None
        return jsonify({"path": path})

    @app.route("/api/pick-files", methods=["POST"])
    def pick_files_route():

        if shared.window is None:
            return jsonify({"paths": None})
        import webview
        open_dialog = getattr(getattr(webview, "FileDialog", None), "OPEN", None)
        if open_dialog is None:
            open_dialog = webview.OPEN_DIALOG
        multiple = bool((request.get_json(silent=True) or {}).get("multiple", True))
        result = shared.window.create_file_dialog(open_dialog, allow_multiple=multiple)

        return jsonify({"paths": list(result) if result else []})
