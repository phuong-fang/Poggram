import os

from flask import current_app, jsonify, request

import shared

import store
import telegram_client

def register(app):
    @app.route("/api/settings/video-player", methods=["PUT"])
    def update_video_player_path():

        fields = request.get_json(force=True) or {}
        update = {}
        if "video_player_path" in fields:
            path = (fields.get("video_player_path") or "").strip()
            if path and not os.path.isfile(path):
                return jsonify({"error": "That path doesn't point to an existing file."}), 400
            update["video_player_path"] = path or None
        if "external_video_player_enabled" in fields:
            update["external_video_player_enabled"] = bool(fields["external_video_player_enabled"])
        store.save_settings_fields(update)
        settings = store.load_settings()
        return jsonify({
            "video_player_path": settings.get("video_player_path") or shared.detect_video_player(),
            "external_video_player_enabled": settings.get("external_video_player_enabled", False),
        })

    @app.route("/api/settings/max-chunk-size", methods=["PUT"])
    def update_max_chunk_size():
        fields = request.get_json(force=True) or {}
        try:
            value = int(fields.get("max_chunk_size_bytes"))
        except (TypeError, ValueError):
            return jsonify({"error": "max_chunk_size_bytes must be a whole number of bytes."}), 400
        if value < 1_000_000:
            return jsonify({"error": "Chunk size must be at least 1,000,000 bytes (1 MB)."}), 400
        store.save_settings_fields({"max_chunk_size_bytes": value})

        return jsonify(telegram_client.status())

    @app.route("/api/settings/parallel-transfers", methods=["PUT"])
    def update_parallel_transfers():
        fields = request.get_json(force=True) or {}
        try:
            value = int(fields.get("max_parallel_transfers"))
        except (TypeError, ValueError):
            return jsonify({"error": "max_parallel_transfers must be a whole number."}), 400
        value = max(1, min(10, value))
        store.save_settings_fields({"max_parallel_transfers": value})
        return jsonify({"max_parallel_transfers": value})

    @app.route("/api/settings/max-upload-request-size", methods=["PUT"])
    def update_max_upload_request_size():

        fields = request.get_json(force=True) or {}
        try:
            value = int(fields.get("max_upload_request_bytes"))
        except (TypeError, ValueError):
            return jsonify({"error": "max_upload_request_bytes must be a whole number of bytes (0 = no limit)."}), 400
        if value < 0:
            return jsonify({"error": "Must be 0 (no limit) or a positive number of bytes."}), 400
        if 0 < value < 1024 * 1024 * 1024:
            return jsonify({"error": "Must be at least 1 GB, or 0 for no limit."}), 400
        store.save_settings_fields({"max_upload_request_bytes": value})
        current_app.config["MAX_CONTENT_LENGTH"] = value if value > 0 else None
        return jsonify({"max_upload_request_bytes": value})

    @app.route("/api/settings/max-cache-size", methods=["PUT"])
    def update_max_cache_size():
        fields = request.get_json(force=True) or {}
        try:
            value = int(fields.get("max_cache_bytes"))
        except (TypeError, ValueError):
            return jsonify({"error": "max_cache_bytes must be a whole number of bytes."}), 400
        if value < 0:
            return jsonify({"error": "Cache size must be 0 (unlimited) or a positive number of bytes."}), 400
        store.save_settings_fields({"max_cache_bytes": value})
        return jsonify({"max_cache_bytes": value, "current_usage": store.cache_disk_usage()})

    @app.route("/api/settings/upload", methods=["PUT"])
    def update_upload_settings():

        fields = request.get_json(force=True) or {}
        try:
            workers = int(fields.get("upload_parallel_workers"))
        except (TypeError, ValueError):
            return jsonify({"error": "upload_parallel_workers must be a whole number."}), 400
        try:
            part_kb = int(fields.get("upload_part_size_kb"))
        except (TypeError, ValueError):
            return jsonify({"error": "upload_part_size_kb must be a whole number of KB (0 = auto)."}), 400
        workers = max(1, min(16, workers))
        part_kb = 0 if part_kb == 0 else max(32, min(512, part_kb))
        store.save_settings_fields({
            "upload_parallel_workers": workers,
            "upload_part_size_kb": part_kb,
        })
        return jsonify({
            "upload_parallel_workers": workers,
            "upload_part_size_kb": part_kb,
        })

    @app.route("/api/settings/completed-uploads-persistence", methods=["PUT"])
    def update_completed_uploads_persistence():

        fields = request.get_json(force=True) or {}
        value = fields.get("completed_uploads_persistence")
        if value not in ("clear", "keep"):
            return jsonify({"error": "completed_uploads_persistence must be 'clear' or 'keep'."}), 400
        store.save_settings_fields({"completed_uploads_persistence": value})

        if value == "clear":
            store.clear_completed_uploads()
        return jsonify({"completed_uploads_persistence": value})

    @app.route("/api/settings/close-to-tray", methods=["PUT"])
    def update_close_to_tray():

        fields = request.get_json(force=True) or {}
        value = bool(fields.get("close_to_tray"))
        store.save_settings_fields({"close_to_tray": value})
        return jsonify({"close_to_tray": value})

    @app.route("/api/logs/open", methods=["POST"])
    def open_log_file():

        path = os.path.join(store.DATA_DIR, "poggram.log")
        if not os.path.isfile(path):
            return jsonify({"error": "No log file yet - it appears once the app has logged something."}), 404
        try:
            os.startfile(path)
        except AttributeError:
            import subprocess

            subprocess.Popen(["xdg-open", path])
        except Exception as e:
            return jsonify({"error": shared.client_error(e)}), 500
        return jsonify({"ok": True, "path": path})

    @app.route("/api/settings/download", methods=["PUT"])
    def update_download_settings():

        fields = request.get_json(force=True) or {}
        try:
            workers = int(fields.get("download_parallel_workers"))
        except (TypeError, ValueError):
            return jsonify({"error": "download_parallel_workers must be a whole number."}), 400
        workers = max(1, min(16, workers))
        store.save_settings_fields({"download_parallel_workers": workers})
        return jsonify({"download_parallel_workers": workers})

    @app.route("/api/settings/thumbnail-format", methods=["PUT"])
    def update_thumbnail_format():

        fields = request.get_json(force=True) or {}
        value = fields.get("thumbnail_format")
        if value not in ("jpeg", "avif"):
            return jsonify({"error": 'thumbnail_format must be "jpeg" or "avif".'}), 400
        store.save_settings_fields({"thumbnail_format": value})
        return jsonify({"thumbnail_format": value})

    @app.route("/api/settings/thumbnail-quality", methods=["PUT"])
    def update_thumbnail_quality():

        fields = request.get_json(force=True) or {}
        try:
            value = int(fields.get("thumbnail_quality"))
        except (TypeError, ValueError):
            return jsonify({"error": "thumbnail_quality must be a whole number."}), 400
        value = max(1, min(100, value))
        store.save_settings_fields({"thumbnail_quality": value})
        return jsonify({"thumbnail_quality": value})

    @app.route("/api/settings/thumbnail-chroma-subsampling", methods=["PUT"])
    def update_thumbnail_chroma_subsampling():

        fields = request.get_json(force=True) or {}
        value = fields.get("thumbnail_chroma_subsampling")
        if value not in ("default", "4:4:4", "4:2:2", "4:2:0"):
            return jsonify({"error": 'thumbnail_chroma_subsampling must be "default", "4:4:4", "4:2:2", or "4:2:0".'}), 400
        store.save_settings_fields({"thumbnail_chroma_subsampling": value})
        return jsonify({"thumbnail_chroma_subsampling": value})

    @app.route("/api/settings/sync-backoff", methods=["PUT"])
    def update_sync_backoff():

        fields = request.get_json(force=True) or {}
        try:
            value = int(fields.get("sync_backoff_workers"))
        except (TypeError, ValueError):
            return jsonify({"error": "sync_backoff_workers must be a whole number."}), 400
        cap = int(store.load_settings().get("upload_parallel_workers") or 3)
        value = max(1, min(cap, value))
        store.save_settings_fields({"sync_backoff_workers": value})
        return jsonify({"sync_backoff_workers": value})

    _SETTINGS_EXPORT_ALLOWLIST = {
        "archive_chat_id", "archive_chat_title", "is_premium", "max_chunk_size_bytes",
        "app_data_backup_enabled", "app_data_backup_check_on_boot",
    }

    @app.route("/api/settings/export", methods=["GET"])
    def export_settings():
        try:
            s = store.load_settings()
            safe = {k: v for k, v in s.items() if k in _SETTINGS_EXPORT_ALLOWLIST}
            return jsonify({"ok": True, "settings": safe})
        except Exception as e:
            return jsonify({"ok": False, "error": shared.client_error(e)}), 400

    @app.route("/api/settings/import", methods=["POST"])
    def import_settings():
        fields = request.get_json(force=True) or {}
        settings = fields.get("settings")
        if not settings or not isinstance(settings, dict):
            return jsonify({"ok": False, "error": "No settings provided"}), 400

        safe = {k: v for k, v in settings.items() if k in _SETTINGS_EXPORT_ALLOWLIST}
        try:
            store.save_settings_fields(safe)
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "error": shared.client_error(e)}), 400
