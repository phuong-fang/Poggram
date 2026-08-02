import io

import pytest
from PIL import Image

import thumbnails

def _make_test_image(width, height, mode="RGB"):
    buf = io.BytesIO()
    im = Image.new(mode, (width, height), color=(200, 50, 50) if mode == "RGB" else 128)
    im.save(buf, format="PNG")
    buf.seek(0)
    return buf

def test_generate_image_thumbnail_jpeg_default():
    src = _make_test_image(800, 600)
    result = thumbnails.generate_image_thumbnail(src)
    assert result is not None
    out = Image.open(io.BytesIO(result))
    assert out.format == "JPEG"

def test_generate_image_thumbnail_avif_format():
    src = _make_test_image(800, 600)
    result = thumbnails.generate_image_thumbnail(src, fmt="avif")
    assert result is not None

    assert result[4:8] == b"ftyp"

def test_generate_image_thumbnail_never_upscales():

    src = _make_test_image(100, 50)
    result = thumbnails.generate_image_thumbnail(src)
    out = Image.open(io.BytesIO(result))
    assert out.size == (100, 50)

def test_generate_image_thumbnail_caps_at_320_preserving_aspect():
    src = _make_test_image(1600, 800)
    result = thumbnails.generate_image_thumbnail(src)
    out = Image.open(io.BytesIO(result))
    assert max(out.size) <= 320

    assert abs(out.size[0] / out.size[1] - 2.0) < 0.05

def test_generate_image_thumbnail_converts_rgba_source():

    src = _make_test_image(200, 200, mode="RGBA")
    result = thumbnails.generate_image_thumbnail(src)
    assert result is not None
    out = Image.open(io.BytesIO(result))
    assert out.mode == "RGB"

def test_generate_image_thumbnail_higher_quality_is_larger():
    src = _make_test_image(320, 320)
    low = thumbnails.generate_image_thumbnail(src, quality=30)
    src.seek(0)
    high = thumbnails.generate_image_thumbnail(src, quality=95)
    assert len(high) > len(low)

def test_generate_image_thumbnail_corrupt_data_returns_none():

    garbage = io.BytesIO(b"this is not an image")
    result = thumbnails.generate_image_thumbnail(garbage)
    assert result is None

def test_probe_media_info_missing_ffprobe_returns_none(monkeypatch):
    monkeypatch.setattr(thumbnails.shutil, "which", lambda name: None)
    assert thumbnails.probe_media_info("/nonexistent/path") is None
