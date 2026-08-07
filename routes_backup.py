from flask import jsonify, request
import threading

import shared
import store
import telegram_client
import logging

logger = logging.getLogger(__name__)

def register(app):

    _restore_lock = threading.Lock()

    _backup_lock = threading.Lock()

    @app.route("/api/app-data-backup/status", methods=["GET"])
    def app_data_backup_status_route():
        settings = store.load_settings()
        result = {
            "backup_enabled": settings.get("app_data_backup_enabled", False),
            "check_on_boot": settings.get("app_data_backup_check_on_boot", False),
            "include_thumbnails": settings.get("app_data_backup_include_thumbnails", False),
            "forum_enabled": None,
        }
        try:
            if telegram_client.status().get("connected") and settings.get("archive_chat_id"):
                result["forum_enabled"] = telegram_client.is_forum_enabled()
        except Exception:
            logger.exception("Failed to check forum-mode status")
        return jsonify(result)

    @app.route("/api/app-data-backup/forum-mode", methods=["POST"])
    def app_data_backup_forum_mode_route():

        fields = request.get_json(force=True) or {}
        enabled = bool(fields.get("enabled"))
        if not enabled:
            return jsonify({
                "ok": False,
                "error": "Topics/Forum mode can't be turned off - app-data backup can't store anything without it.",
            }), 400
        try:
            telegram_client.set_forum_mode(enabled)
            return jsonify({"ok": True, "forum_enabled": enabled})
        except Exception as e:
            logger.exception(f"Failed to set forum mode to {enabled}")
            return jsonify({"ok": False, "error": shared.client_error(e)}), 400

    @app.route("/api/app-data-backup/settings", methods=["POST"])
    def app_data_backup_settings_route():
        fields = request.get_json(force=True) or {}
        update = {}
        if "backup_enabled" in fields:
            update["app_data_backup_enabled"] = bool(fields["backup_enabled"])
        if "check_on_boot" in fields:
            update["app_data_backup_check_on_boot"] = bool(fields["check_on_boot"])
        if "include_thumbnails" in fields:
            update["app_data_backup_include_thumbnails"] = bool(fields["include_thumbnails"])
        settings = store.save_settings_fields(update)
        if update.get("app_data_backup_enabled"):

            shared.mark_app_data_changed()
        return jsonify({
            "backup_enabled": settings.get("app_data_backup_enabled", False),
            "check_on_boot": settings.get("app_data_backup_check_on_boot", False),
            "include_thumbnails": settings.get("app_data_backup_include_thumbnails", False),
        })

    @app.route("/api/app-data-backup/snapshot", methods=["POST"])
    def app_data_backup_snapshot_route():

        if not _backup_lock.acquire(blocking=False):
            return jsonify({"ok": False, "error": "A backup is already in progress."}), 409

        try:
            shared.run_app_data_backup(on_finished=_backup_lock.release)
        except Exception as e:
            _backup_lock.release()
            logger.exception("Failed to start app-data backup")
            return jsonify({"ok": False, "error": shared.client_error(e)}), 400
        return jsonify({"ok": True, "started": True})

    @app.route("/api/app-data-backup/backup-status", methods=["GET"])
    def app_data_backup_backup_status_route():

        with shared.backup_status_lock:
            return jsonify(dict(shared.backup_status))

    @app.route("/api/app-data-backup/snapshots", methods=["GET"])
    def app_data_backup_snapshots_route():
        try:
            return jsonify(telegram_client.list_app_data_snapshots())
        except Exception as e:
            logger.exception("Failed to list app-data snapshots")
            return jsonify({"error": shared.client_error(e)}), 400

    @app.route("/api/app-data-backup/snapshots/<int:message_id>/restore", methods=["POST"])
    def app_data_backup_restore_route(message_id):

        if not _restore_lock.acquire(blocking=False):
            return jsonify({"ok": False, "error": "A restore operation is already in progress."}), 409

        try:
            shared.run_app_data_restore(message_id, on_finished=_restore_lock.release)
        except Exception as e:
            _restore_lock.release()
            logger.exception("Failed to start app-data restore")
            return jsonify({"ok": False, "error": shared.client_error(e)}), 400
        return jsonify({"ok": True, "started": True})

    @app.route("/api/app-data-backup/restore-status", methods=["GET"])
    def app_data_backup_restore_status_route():

        with shared.restore_status_lock:
            return jsonify(dict(shared.restore_status))

    @app.route("/api/app-data-backup/check-latest", methods=["GET"])
    def app_data_backup_check_latest_route():

        try:
            snapshots = telegram_client.list_app_data_snapshots()
        except Exception as e:
            logger.exception("Boot-time app-data backup check failed")
            return jsonify({"error": shared.client_error(e)}), 400
        if not snapshots:
            return jsonify({"newer_available": False})
        latest = snapshots[0]
        last_known = store.load_settings().get("app_data_backup_last_known_message_id")
        newer = last_known is None or latest["message_id"] > last_known
        return jsonify({"newer_available": newer, "latest": latest})
