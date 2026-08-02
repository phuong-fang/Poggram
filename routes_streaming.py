import os
import subprocess
import unicodedata
from urllib.parse import quote

from flask import Response, jsonify, request

import store
import telegram_client
import thumbnails
import shared

def _content_disposition(filename: str) -> str:

    base, ext = os.path.splitext(filename)

    def _asciify(value):
        stripped = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")

        return stripped.replace('"', "").replace("\\", "").strip()

    ascii_name = (_asciify(base) or "download") + _asciify(ext)
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename, safe='')}"

def _sniff_thumbnail_mimetype(data: bytes) -> str:

    if data[4:8] == b"ftyp":
        return "image/avif"
    return "image/jpeg"

def _thumbnail_ext_for_bytes(data: bytes) -> str:

    return "avif" if data[4:8] == b"ftyp" else "jpg"

def _local_thumbnail_encode_settings():

    settings = store.load_settings()
    return {
        "fmt": settings.get("thumbnail_format") or "jpeg",
        "quality": settings.get("thumbnail_quality"),
        "subsampling": settings.get("thumbnail_chroma_subsampling"),
    }

def register(app):
    def _chunk_boundaries(chunks):

        boundaries = []
        offset = 0
        for chunk in chunks:
            boundaries.append((offset, offset + chunk["size_bytes"]))
            offset += chunk["size_bytes"]
        return boundaries

    def _chunks_for_range(boundaries, start, end):

        spans = []
        for i, (cstart, cend) in enumerate(boundaries):
            overlap_start = max(start, cstart)
            overlap_end = min(end, cend - 1)
            if overlap_start <= overlap_end:
                spans.append((i, overlap_start - cstart, overlap_end - cstart))
        return spans

    def _parse_range(range_header, total_size):

        if not range_header or not range_header.startswith("bytes=") or total_size == 0:
            return None
        spec = range_header[len("bytes="):].split(",")[0].strip()
        if "-" not in spec:
            return None
        start_str, end_str = spec.split("-", 1)
        try:
            if start_str == "":
                if end_str == "":
                    return None
                length = int(end_str)
                start, end = max(0, total_size - length), total_size - 1
            else:
                start = int(start_str)
                end = int(end_str) if end_str else total_size - 1
        except ValueError:
            return None
        end = min(end, total_size - 1)
        if start > end or start < 0:
            return None
        return start, end

    def _iter_chunk_range(file, version_index, version, chunk_index, local_start, local_end):

        window = 4 * 1024 * 1024
        cache_file_path = store.cache_path(file["id"], version_index, chunk_index)
        if version["cached_chunks"][chunk_index] and os.path.exists(cache_file_path):
            with open(cache_file_path, "rb") as f:
                f.seek(local_start)
                remaining = local_end - local_start + 1
                while remaining > 0:
                    data = f.read(min(window, remaining))
                    if not data:
                        break
                    remaining -= len(data)
                    yield data
            return
        chunk = version["chunks"][chunk_index]
        download_workers = int(store.load_settings().get("download_parallel_workers") or 8)
        yield from telegram_client.download_range_parallel(
            file["telegram_chat_id"], chunk["message_id"], local_start, local_end - local_start + 1,
            num_workers=download_workers,
        )

    def _yield_file(path):
        window = 4 * 1024 * 1024
        with open(path, "rb") as f:
            while True:
                data = f.read(window)
                if not data:
                    break
                yield data

    def _maybe_generate_thumbnail(file_id, version_index, chunk_index, chunk_path, version, is_image, is_video, file=None):

        if (
            version_index == (file["current_version"] if file else version_index)
            and len(version["chunks"]) == 1
            and (is_image or is_video)
            and store.find_thumbnail_path(file_id, version_index) is None
        ):
            enc = _local_thumbnail_encode_settings()
            if is_image:
                thumb_bytes = thumbnails.generate_image_thumbnail(chunk_path, **enc)
            else:
                thumb_bytes = thumbnails.generate_video_thumbnail(chunk_path, **enc)
            if thumb_bytes:

                store.write_thumbnail_cache(
                    file_id, version_index, thumb_bytes, store.thumbnail_ext_for_format(enc["fmt"])
                )

    def _serve_full(file, version_index, cache_chunks=True):

        file_id = file["id"]
        version = file["versions"][version_index]
        os.makedirs(store.CACHE_DIR, exist_ok=True)
        boundaries = _chunk_boundaries(version["chunks"])

        version_mime_type = version.get("mime_type")
        _is_image = bool(version_mime_type) and version_mime_type.startswith("image/")
        _is_video = bool(version_mime_type) and version_mime_type.startswith("video/")

        def _generate():
            for i, (cstart, cend) in enumerate(boundaries):
                path = store.cache_path(file_id, version_index, i)
                if version["cached_chunks"][i] and os.path.exists(path):
                    yield from _yield_file(path)
                    _maybe_generate_thumbnail(file_id, version_index, i, path, version, _is_image, _is_video, file)
                    continue
                chunk_size = cend - cstart
                message_id = version["chunks"][i]["message_id"]
                if not cache_chunks:

                    download_workers = int(store.load_settings().get("download_parallel_workers") or 8)
                    yield from telegram_client.download_range_parallel(
                        file["telegram_chat_id"], message_id, 0, chunk_size,
                        num_workers=download_workers,
                    )
                    continue
                partial_path = store.partial_cache_path(file_id, version_index, i)

                with shared.chunk_lock(file_id, version_index, i):
                    if os.path.exists(path):

                        yield from _yield_file(path)
                        _maybe_generate_thumbnail(file_id, version_index, i, path, version, _is_image, _is_video, file)
                        continue
                    resume_offset = min(os.path.getsize(partial_path), chunk_size) if os.path.exists(partial_path) else 0
                    if resume_offset:
                        yield from _yield_file(partial_path)
                    if resume_offset < chunk_size:

                        download_workers = int(store.load_settings().get("download_parallel_workers") or 8)
                        with open(partial_path, "ab") as out:
                            for data in telegram_client.download_range_parallel(
                                file["telegram_chat_id"], message_id, resume_offset, chunk_size - resume_offset,
                                num_workers=download_workers,
                            ):
                                out.write(data)
                                yield data

                    actual_size = os.path.getsize(partial_path)
                    if actual_size != chunk_size:
                        import logging
                        logging.getLogger(__name__).error(
                            f"_serve_full: chunk {i} of {file_id} came back short "
                            f"({actual_size} of {chunk_size} bytes) - leaving uncached for retry"
                        )
                        continue
                    os.replace(partial_path, path)
                store.mark_chunk_cached(file_id, version_index, i)
                _maybe_generate_thumbnail(file_id, version_index, i, path, version, _is_image, _is_video, file)
                store.prune_cache()

        headers = {
            "Content-Length": str(version["size_bytes"]),
            "Content-Disposition": _content_disposition(file["name"]),
            "Accept-Ranges": "bytes",
        }
        return Response(_generate(), mimetype=version.get("mime_type") or "application/octet-stream", headers=headers)

    def _serve_range(file, version_index, range_header):
        version = file["versions"][version_index]
        total_size = version["size_bytes"]
        parsed = _parse_range(range_header, total_size)
        if parsed is None:
            return Response(status=416, headers={"Content-Range": f"bytes */{total_size}"})
        start, end = parsed
        boundaries = _chunk_boundaries(version["chunks"])
        spans = _chunks_for_range(boundaries, start, end)

        def _generate():
            for i, local_start, local_end in spans:
                yield from _iter_chunk_range(file, version_index, version, i, local_start, local_end)

        headers = {
            "Content-Range": f"bytes {start}-{end}/{total_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(end - start + 1),
            "Content-Disposition": _content_disposition(file["name"]),
        }
        return Response(
            _generate(), status=206, mimetype=version.get("mime_type") or "application/octet-stream", headers=headers
        )

    @app.route("/api/files/<file_id>/content")
    def file_content(file_id):
        file = store.find_file(file_id)
        if file is None:
            return jsonify({"error": "not found"}), 404
        version_index = file["current_version"]
        range_header = request.headers.get("Range")
        if range_header:
            return _serve_range(file, version_index, range_header)
        return _serve_full(file, version_index, cache_chunks=request.args.get("cache") != "0")

    @app.route("/api/files/<file_id>/versions/<int:version_index>/content")
    def file_version_content_route(file_id, version_index):
        file = store.find_file(file_id)
        if file is None:
            return jsonify({"error": "not found"}), 404
        if version_index < 0 or version_index >= len(file["versions"]):
            return jsonify({"error": "version not found"}), 404
        range_header = request.headers.get("Range")
        if range_header:
            return _serve_range(file, version_index, range_header)
        return _serve_full(file, version_index, cache_chunks=request.args.get("cache") != "0")

    @app.route("/api/files/<file_id>/thumbnail")
    def file_thumbnail_route(file_id):

        file = store.find_file(file_id)
        if file is None:
            return jsonify({"error": "not found"}), 404
        version_index = file["current_version"]
        version = store.current_version(file)
        local_path = store.find_thumbnail_path(file_id, version_index)
        if local_path is not None:
            with open(local_path, "rb") as f:
                cached_bytes = f.read()
            return Response(cached_bytes, mimetype=_sniff_thumbnail_mimetype(cached_bytes))

        thumb_bytes = None
        if version.get("has_thumbnail"):
            try:

                thumb_bytes = telegram_client.download_thumbnail(
                    file["telegram_chat_id"], version["chunks"][0]["message_id"]
                )
            except Exception:

                import logging
                logging.getLogger(__name__).exception()
                thumb_bytes = None

        mime_type = version.get("mime_type")
        if not thumb_bytes and mime_type and mime_type.startswith("video/"):
            thumb_bytes = thumbnails.generate_video_thumbnail(
                f"http://{request.host}/api/files/{file_id}/content", **_local_thumbnail_encode_settings()
            )

        if not thumb_bytes:
            return Response(status=404)
        store.write_thumbnail_cache(file_id, version_index, thumb_bytes, _thumbnail_ext_for_bytes(thumb_bytes))
        return Response(thumb_bytes, mimetype=_sniff_thumbnail_mimetype(thumb_bytes))

    @app.route("/api/files/<file_id>/thumbnail/from-frame", methods=["POST"])
    def set_thumbnail_from_frame_route(file_id):

        file = store.find_file(file_id)
        if file is None:
            return jsonify({"error": "not found"}), 404
        version = store.current_version(file)
        mime_type = version.get("mime_type")
        if not mime_type or not mime_type.startswith("video/"):
            return jsonify({"error": "Only video files support picking a thumbnail frame."}), 400
        fields = request.get_json(force=True) or {}
        try:
            seconds = float(fields.get("seconds"))
        except (TypeError, ValueError):
            return jsonify({"error": "seconds must be a number."}), 400
        if seconds < 0:
            return jsonify({"error": "seconds must be 0 or positive."}), 400
        enc = _local_thumbnail_encode_settings()
        thumb_bytes = thumbnails.generate_video_thumbnail(
            f"http://{request.host}/api/files/{file_id}/content", seek_seconds=seconds, **enc
        )
        if not thumb_bytes:
            return jsonify({"error": "Couldn't extract a frame at that timestamp."}), 400
        version_index = file["current_version"]

        store.write_thumbnail_cache(file_id, version_index, thumb_bytes, store.thumbnail_ext_for_format(enc["fmt"]))
        return jsonify({"ok": True})

    @app.route("/api/files/<file_id>/play-external", methods=["POST"])
    def play_file_externally(file_id):
        file = store.find_file(file_id)
        if file is None:
            return jsonify({"error": "File not found."}), 404
        settings = store.load_settings()

        if not settings.get("external_video_player_enabled"):
            return jsonify({"error": "External video player is turned off - enable it in Settings first."}), 400
        player_path = settings.get("video_player_path") or shared.detect_video_player()
        if not player_path or not os.path.isfile(player_path):
            return jsonify({
                "error": "No video player found - set one in Settings (Video player path).",
            }), 400
        stream_url = request.host_url.rstrip("/") + f"/api/files/{file_id}/content"
        try:
            subprocess.Popen([player_path, stream_url])
        except OSError as e:
            return jsonify({"error": f"Couldn't launch player: {e}"}), 500
        return jsonify({"ok": True})
