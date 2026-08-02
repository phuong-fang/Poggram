import os
import time

import pytest

import store
from tests.conftest import isolated_store

def _make_thumb(isolated_store, file_id, version_index, ext, content):
    path = isolated_store.thumbnail_path_for_ext(file_id, version_index, ext)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)
    return path

def test_snapshot_round_trip_preserves_folders_and_files(isolated_store):
    folder, _ = isolated_store.create_folder("Backed Up")
    file = isolated_store.create_file({
        "name": "video.mp4", "folder_id": folder["id"], "size_bytes": 123,
        "mime_type": "video/mp4", "telegram_chat_id": "-100123", "chunks": [{"message_id": 1, "size_bytes": 123}],
    })

    snapshot_bytes = isolated_store.build_app_data_snapshot()

    isolated_store.save_folders([])
    isolated_store.save_files([])
    assert isolated_store.load_folders() == []
    assert isolated_store.load_files() == []

    isolated_store.restore_app_data_snapshot(snapshot_bytes)

    restored_folders = isolated_store.load_folders()
    restored_files = isolated_store.load_files()
    assert len(restored_folders) == 1
    assert restored_folders[0]["name"] == "Backed Up"
    assert len(restored_files) == 1
    assert restored_files[0]["name"] == "video.mp4"
    assert restored_files[0]["id"] == file["id"]

def test_snapshot_round_trip_preserves_thumbnails_both_formats(isolated_store):

    _make_thumb(isolated_store, "abc12345", 0, "jpg", b"\xff\xd8\xff fake jpeg bytes")
    _make_thumb(isolated_store, "def67890", 0, "avif", b"fake avif bytes")

    snapshot_bytes = isolated_store.build_app_data_snapshot()

    for name in os.listdir(store.CACHE_DIR):
        os.remove(os.path.join(store.CACHE_DIR, name))
    assert isolated_store.find_thumbnail_path("abc12345", 0) is None
    assert isolated_store.find_thumbnail_path("def67890", 0) is None

    isolated_store.restore_app_data_snapshot(snapshot_bytes)

    jpg_path = isolated_store.find_thumbnail_path("abc12345", 0)
    avif_path = isolated_store.find_thumbnail_path("def67890", 0)
    assert jpg_path is not None and jpg_path.endswith(".jpg")
    assert avif_path is not None and avif_path.endswith(".avif")
    with open(jpg_path, "rb") as f:
        assert f.read() == b"\xff\xd8\xff fake jpeg bytes"
    with open(avif_path, "rb") as f:
        assert f.read() == b"fake avif bytes"

def test_snapshot_restore_is_correct_with_many_thumbnails(isolated_store):

    n = 60
    expected = {}
    for i in range(n):
        file_id = f"{i:08x}"
        content = f"thumbnail content for file {i}".encode() * 50
        _make_thumb(isolated_store, file_id, 0, "jpg", content)
        expected[file_id] = content

    snapshot_bytes = isolated_store.build_app_data_snapshot()

    for name in os.listdir(store.CACHE_DIR):
        os.remove(os.path.join(store.CACHE_DIR, name))

    t0 = time.time()
    isolated_store.restore_app_data_snapshot(snapshot_bytes)
    elapsed = time.time() - t0

    for file_id, content in expected.items():
        path = isolated_store.find_thumbnail_path(file_id, 0)
        assert path is not None, f"thumbnail for {file_id} missing after restore"
        with open(path, "rb") as f:
            assert f.read() == content

    assert elapsed < 10.0, f"restore took {elapsed:.1f}s for {n} thumbnails - possible O(n^2) regression"

def test_legacy_zip_snapshot_still_restores(isolated_store):

    import io
    import json
    import zipfile

    folder_data = [{"id": "f1", "name": "Legacy", "parent_id": None,
                     "date_created": "2020-01-01T00:00:00", "date_modified": "2020-01-01T00:00:00",
                     "deleted": False, "date_deleted": None}]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("folders.json", json.dumps(folder_data))
        zf.writestr("files.json", json.dumps([]))
        zf.writestr("cache/aaaa1111_v0_thumb.jpg", b"legacy jpeg bytes")
    snapshot_bytes = buf.getvalue()

    isolated_store.restore_app_data_snapshot(snapshot_bytes)

    restored_folders = isolated_store.load_folders()
    assert len(restored_folders) == 1
    assert restored_folders[0]["name"] == "Legacy"
    thumb_path = isolated_store.find_thumbnail_path("aaaa1111", 0)
    assert thumb_path is not None
    with open(thumb_path, "rb") as f:
        assert f.read() == b"legacy jpeg bytes"
