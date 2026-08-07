import io
import json
import shutil
import subprocess

import pillow_avif
from PIL import Image

_MAX_DIMENSIONS = (320, 320)
_JPEG_QUALITY = 75
_AVIF_QUALITY = 65

_FFMPEG_TIMEOUT_SECONDS = 45

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_VALID_SUBSAMPLING = ("4:4:4", "4:2:2", "4:2:0")

def _resize_to_thumbnail(source, fmt="jpeg", quality=None, subsampling=None):

    try:
        with Image.open(source) as im:
            im.load()

            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            im.thumbnail(_MAX_DIMENSIONS)
            buffer = io.BytesIO()
            save_kwargs = {}
            if subsampling in _VALID_SUBSAMPLING:
                save_kwargs["subsampling"] = subsampling
            if fmt == "avif":
                im.save(buffer, format="AVIF", quality=quality or _AVIF_QUALITY, **save_kwargs)
            else:
                im.save(buffer, format="JPEG", quality=quality or _JPEG_QUALITY, **save_kwargs)
            return buffer.getvalue()
    except Exception:
        return None

def generate_image_thumbnail(source_path, fmt="jpeg", quality=None, subsampling=None):

    return _resize_to_thumbnail(source_path, fmt=fmt, quality=quality, subsampling=subsampling)

_VIDEO_FRAME_SEEK_SECONDS = "1"

def _extract_video_frame(source_path, seek_seconds=_VIDEO_FRAME_SEEK_SECONDS):

    if shutil.which("ffmpeg") is None:
        return None

    def _run(args):
        try:

            result = subprocess.run(args, capture_output=True, timeout=_FFMPEG_TIMEOUT_SECONDS,
                                    creationflags=_NO_WINDOW)
            return result.stdout if result.returncode == 0 and result.stdout else None
        except Exception:
            return None

    base = ["ffmpeg", "-nostdin", "-loglevel", "error"]
    tail = ["-frames:v", "1", "-f", "image2", "-vcodec", "mjpeg", "-q:v", "3", "pipe:1"]

    frame = _run([*base, "-ss", str(seek_seconds), "-i", source_path, *tail])
    if frame is not None:
        return frame
    return _run([*base, "-i", source_path, *tail])

def generate_video_thumbnail(source_path, seek_seconds=None, fmt="jpeg", quality=None, subsampling=None):

    frame_bytes = _extract_video_frame(
        source_path, **({} if seek_seconds is None else {"seek_seconds": seek_seconds})
    )
    if frame_bytes is None:
        return None
    return _resize_to_thumbnail(io.BytesIO(frame_bytes), fmt=fmt, quality=quality, subsampling=subsampling)

def probe_media_info(source):

    if shutil.which("ffprobe") is None:
        return None
    try:
        result = subprocess.run(

            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", "-i", source],
            capture_output=True, timeout=_FFMPEG_TIMEOUT_SECONDS,
            creationflags=_NO_WINDOW,
        )
        if result.returncode != 0 or not result.stdout:
            return None
        data = json.loads(result.stdout)
    except Exception:
        return None

    info = {}
    duration = (data.get("format") or {}).get("duration")
    if duration is not None:
        try:
            info["duration_seconds"] = float(duration)
        except (TypeError, ValueError):
            pass
    streams = data.get("streams") or []
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video_stream:
        if video_stream.get("width") and video_stream.get("height"):
            info["width"] = video_stream["width"]
            info["height"] = video_stream["height"]
        if video_stream.get("codec_name"):
            info["video_codec"] = video_stream["codec_name"]

    if audio_stream and audio_stream.get("codec_name"):
        info["audio_codec"] = audio_stream["codec_name"]
    return info or None
