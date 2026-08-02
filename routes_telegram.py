from flask import jsonify, request

import shared
import os

import store
import version
import telegram_client
import logging

logger = logging.getLogger(__name__)

def register(app):
    @app.route("/api/telegram/status", methods=["GET"])
    def telegram_status():
        result = telegram_client.status()
        settings = store.load_settings()

        result["api_id"] = settings.get("api_id")
        result["api_hash"] = settings.get("api_hash")
        result["video_player_path"] = settings.get("video_player_path") or shared.detect_video_player()
        result["external_video_player_enabled"] = settings.get("external_video_player_enabled", False)
        result["max_parallel_transfers"] = settings.get("max_parallel_transfers", 3)
        result["upload_parallel_workers"] = settings.get("upload_parallel_workers", 8)
        result["upload_part_size_kb"] = settings.get("upload_part_size_kb", 0)
        result["download_parallel_workers"] = settings.get("download_parallel_workers", 8)
        result["max_cache_bytes"] = settings.get("max_cache_bytes", 0)
        result["sync_backoff_workers"] = settings.get("sync_backoff_workers", 1)
        result["max_upload_request_bytes"] = settings.get("max_upload_request_bytes", 64_000_000_000)
        result["thumbnail_format"] = settings.get("thumbnail_format", "jpeg")
        result["thumbnail_quality"] = settings.get("thumbnail_quality", 75)
        result["thumbnail_chroma_subsampling"] = settings.get("thumbnail_chroma_subsampling", "default")
        result["close_to_tray"] = settings.get("close_to_tray", True)
        result["app_version"] = version.describe()
        result["log_path"] = os.path.join(store.DATA_DIR, "poggram.log")
        return jsonify(result)

    @app.route("/api/telegram/logout", methods=["POST"])
    def telegram_logout_route():

        try:
            telegram_client.logout()
            return jsonify({"ok": True})
        except Exception as e:
            logger.exception("Logout failed")
            return jsonify({"ok": False, "error": str(e) or type(e).__name__}), 400

    @app.route("/api/telegram/refresh-premium-status", methods=["POST"])
    def telegram_refresh_premium_status_route():

        try:
            is_premium = telegram_client.refresh_premium_status()
            settings = store.load_settings()
            return jsonify({
                "ok": True,
                "is_premium": is_premium,
                "max_chunk_size_bytes": settings.get("max_chunk_size_bytes"),
            })
        except Exception as e:
            logger.exception("Failed to refresh Premium status")
            return jsonify({"ok": False, "error": str(e) or type(e).__name__}), 400

    @app.route("/api/telegram/archive-check", methods=["GET"])
    def telegram_archive_check_route():

        try:
            return jsonify(telegram_client.check_archive_identity())
        except Exception as e:
            logger.exception("Archive identity check failed")
            return jsonify({"error": str(e) or type(e).__name__}), 400

    @app.route("/api/telegram/connect", methods=["POST"])
    def telegram_connect():
        fields = request.get_json(force=True) or {}
        api_id = fields.get("api_id")
        api_hash = (fields.get("api_hash") or "").strip()
        phone_number = (fields.get("phone_number") or "").strip()
        if not api_id or not api_hash or not phone_number:
            return jsonify({"ok": False, "error": "API ID, API hash, and phone number are all required."}), 400
        try:
            telegram_client.connect(api_id, api_hash, phone_number)
            return jsonify({"ok": True, "step": "code"})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 400

    @app.route("/api/telegram/code", methods=["POST"])
    def telegram_code():
        fields = request.get_json(force=True) or {}
        code = (fields.get("code") or "").strip()
        if not code:
            return jsonify({"ok": False, "error": "Enter the code Telegram sent you."}), 400
        try:
            step = telegram_client.submit_code(code)
            return jsonify({"ok": True, "step": step})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 400

    @app.route("/api/telegram/password", methods=["POST"])
    def telegram_password():
        fields = request.get_json(force=True) or {}
        password = fields.get("password") or ""
        if not password:
            return jsonify({"ok": False, "error": "Enter your two-factor authentication password."}), 400
        try:
            telegram_client.submit_password(password)
            return jsonify({"ok": True, "step": "create_archive"})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 400

    @app.route("/api/telegram/create-archive", methods=["POST"])
    def telegram_create_archive():
        fields = request.get_json(force=True) or {}
        title = fields.get("title") or "Poggram Archive"
        try:
            chat_id, chat_title = telegram_client.create_archive_supergroup(title)
            return jsonify({"ok": True, "chat_id": chat_id, "chat_title": chat_title})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 400

    @app.route("/api/telegram/scan-archives", methods=["POST"])
    def telegram_scan_archives():
        try:
            result = telegram_client.scan_archive_candidates()
            if isinstance(result, dict) and "error" in result:
                return jsonify({"ok": False, "error": result["error"]}), 400
            return jsonify({"ok": True, "candidates": result})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 400

    @app.route("/api/telegram/set-archive", methods=["POST"])
    def telegram_set_archive():
        fields = request.get_json(force=True) or {}
        chat_id = fields.get("chat_id")
        title = fields.get("title", "Vault Archive")
        if not chat_id:
            return jsonify({"ok": False, "error": "chat_id is required"}), 400
        try:
            store.save_settings_fields({"archive_chat_id": chat_id, "archive_chat_title": title})
            return jsonify({"ok": True, "chat_id": chat_id, "chat_title": title})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 400

    @app.route("/api/telegram/backfill", methods=["POST"])
    def telegram_backfill():

        force_full = bool((request.get_json(silent=True) or {}).get("full"))
        try:
            imported, skipped = telegram_client.backfill_scan(force_full=force_full)
            return jsonify({"ok": True, "imported": imported, "skipped": skipped, "full": force_full})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 400

    @app.route("/api/media-topic/migrate", methods=["POST"])
    def media_topic_migrate_route():

        try:
            already_migrated = telegram_client.media_topic_message_ids()
        except Exception as e:
            logger.exception("Failed to resolve already-migrated media-topic message ids")
            return jsonify({"ok": False, "error": str(e) or type(e).__name__}), 400

        files = store.load_files()
        migrated = []
        errors = []
        for f in files:
            if f["deleted"] or not f.get("mime_type"):
                continue
            if not (f["mime_type"].startswith("image/") or f["mime_type"].startswith("video/")):
                continue
            for version in f.get("versions", []):
                for chunk in version.get("chunks", []):
                    if chunk["message_id"] in already_migrated:
                        continue
                    old_id = chunk["message_id"]
                    try:
                        new_id = telegram_client.forward_message_to_media_topic(old_id)
                        chunk["message_id"] = new_id
                        store.save_files(files)
                        migrated.append({"file_name": f["name"], "old_message_id": old_id, "new_message_id": new_id})
                    except Exception as e:
                        errors.append({
                            "file_name": f["name"], "old_message_id": old_id, "error": str(e) or type(e).__name__,
                        })
        return jsonify({"ok": True, "migrated": migrated, "errors": errors})
