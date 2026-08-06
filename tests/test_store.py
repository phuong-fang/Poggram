import pytest

import store
from tests.conftest import isolated_store

def test_create_folder(isolated_store):
    folder, error = isolated_store.create_folder("Test Folder")
    assert error is None
    assert folder["name"] == "Test Folder"
    assert folder["id"] is not None
    assert folder["parent_id"] is None

def test_create_subfolder(isolated_store):
    parent, _ = isolated_store.create_folder("Parent")
    child, error = isolated_store.create_folder("Child", parent_id=parent["id"])
    assert error is None
    assert child["parent_id"] == parent["id"]

def test_create_folder_empty_name(isolated_store):
    folder, error = isolated_store.create_folder("")
    assert folder is None
    assert error == "Name is required."

def test_create_folder_invalid_parent(isolated_store):
    folder, error = isolated_store.create_folder("Orphan", parent_id="nonexistent")
    assert folder is None
    assert error == "Parent folder not found."

def test_update_folder_rename(isolated_store):
    folder, _ = isolated_store.create_folder("Original")
    updated, error = isolated_store.update_folder(folder["id"], {"name": "Renamed"})
    assert error is None
    assert updated["name"] == "Renamed"

def test_update_folder_move(isolated_store):
    parent, _ = isolated_store.create_folder("Parent")
    child, _ = isolated_store.create_folder("Child")
    updated, error = isolated_store.update_folder(child["id"], {"parent_id": parent["id"]})
    assert error is None
    assert updated["parent_id"] == parent["id"]

def test_update_folder_move_into_self(isolated_store):
    folder, _ = isolated_store.create_folder("Folder")
    _, error = isolated_store.update_folder(folder["id"], {"parent_id": folder["id"]})
    assert error == "Can't move a folder into itself or its own subfolder."

def test_soft_delete_folder(isolated_store):
    folder, _ = isolated_store.create_folder("ToDelete")
    result = isolated_store.soft_delete_folder(folder["id"])
    assert result is True
    folders = isolated_store.load_folders()

    assert bool(folders[0]["deleted"]) is True

def test_restore_folder(isolated_store):
    folder, _ = isolated_store.create_folder("Deleted")
    isolated_store.soft_delete_folder(folder["id"])
    result, error = isolated_store.restore_folder(folder["id"])
    assert error is None
    assert len(result["restored_folders"]) >= 1
    folders = isolated_store.load_folders()
    assert bool(folders[0]["deleted"]) is False

def test_create_file(isolated_store):
    file = isolated_store.create_file({
        "name": "test.txt",
        "folder_id": None,
        "size_bytes": 100,
        "mime_type": "text/plain",
        "telegram_chat_id": -1001234567890,
        "chunks": [{"message_id": 1, "size_bytes": 100}],
        "source": "app",
    })
    assert file["name"] == "test.txt"
    assert file["size_bytes"] == 100

def test_update_file_star(isolated_store):
    file = isolated_store.create_file({
        "name": "test.txt",
        "folder_id": None,
        "size_bytes": 100,
        "mime_type": "text/plain",
        "telegram_chat_id": -1001234567890,
        "chunks": [{"message_id": 1, "size_bytes": 100}],
        "source": "app",
    })
    updated, error = isolated_store.update_file(file["id"], {"starred": True})
    assert error is None
    assert updated["starred_at"] is not None

def test_update_file_rename(isolated_store):
    file = isolated_store.create_file({
        "name": "original.txt",
        "folder_id": None,
        "size_bytes": 100,
        "mime_type": "text/plain",
        "telegram_chat_id": -1001234567890,
        "chunks": [{"message_id": 1, "size_bytes": 100}],
        "source": "app",
    })
    updated, error = isolated_store.update_file(file["id"], {"name": "renamed.txt"})
    assert error is None
    assert updated["name"] == "renamed.txt"

def test_find_duplicate_by_hash(isolated_store):
    file = isolated_store.create_file({
        "name": "test.txt",
        "folder_id": None,
        "size_bytes": 100,
        "mime_type": "text/plain",
        "telegram_chat_id": -1001234567890,
        "chunks": [{"message_id": 1, "size_bytes": 100}],
        "source": "app",
        "content_hash": "abc123",
    })
    found = isolated_store.find_duplicate_by_hash("abc123")
    assert found is not None
    assert found["id"] == file["id"]

def test_find_duplicate_by_hash_no_match(isolated_store):
    found = isolated_store.find_duplicate_by_hash("nonexistent")
    assert found is None

def test_settings_default(isolated_store):
    settings = isolated_store.load_settings()
    assert settings["max_chunk_size_bytes"] == 1_900_000_000
    assert settings["max_parallel_transfers"] == 3
    assert settings["max_cache_bytes"] == 0

def test_settings_save_and_load(isolated_store):
    isolated_store.save_settings_fields({"max_chunk_size_bytes": 500_000_000})
    settings = isolated_store.load_settings()
    assert settings["max_chunk_size_bytes"] == 500_000_000

def test_cache_path_version_aware(isolated_store):
    path_v0 = isolated_store.cache_path("file1", 0, 0)
    path_v1 = isolated_store.cache_path("file1", 1, 0)
    assert path_v0 != path_v1
    assert "v0" in path_v0
    assert "v1" in path_v1

def test_cache_disk_usage_empty(isolated_store):
    usage = isolated_store.cache_disk_usage()
    assert usage == 0

def test_clear_cache_empty(isolated_store):
    freed = isolated_store.clear_cache()
    assert freed == 0

def test_prune_cache_unlimited(isolated_store):
    freed = isolated_store.prune_cache()
    assert freed == 0

def test_get_or_create_folder_treats_nfc_and_nfd_as_the_same_name(isolated_store):

    import unicodedata

    nfc = unicodedata.normalize("NFC", "Café Photos")
    nfd = unicodedata.normalize("NFD", "Café Photos")
    assert nfc != nfd, "test is meaningless if these are the same string"

    first, err = isolated_store.get_or_create_folder(nfc, None)
    assert err is None
    second, err = isolated_store.get_or_create_folder(nfd, None)
    assert err is None
    assert second["id"] == first["id"], (
        "the same visible name produced two sibling folders - exactly the "
        "duplicate get_or_create_folder exists to prevent"
    )

def test_get_or_create_folder_still_separates_genuinely_different_names(isolated_store):

    a, _ = isolated_store.get_or_create_folder("Cafe", None)
    b, _ = isolated_store.get_or_create_folder("Café", None)
    assert a["id"] != b["id"]

def test_names_in_any_script_survive_a_store_round_trip(isolated_store):

    names = [
        "ホタル 蛍の光.mp4", "中文文件名.zip", "한국어.png", "Привет мир.doc",
        "Ελληνικό.txt", "ملف عربي.pdf", "קובץ עברי.txt", "ไฟล์ไทย.mp4",
        "हिन्दी.jpg", "Phượng Nguyễn.mkv", "trip 🏖️🎉.jpg", "会議 Привет 🎬.mkv",
    ]
    files = [{
        "id": f"f{i}", "name": n, "folder_id": None, "size_bytes": 1,
        "mime_type": "application/octet-stream", "telegram_chat_id": 1,
        "chunks": [], "cached_chunks": [], "versions": [],
        "date_uploaded": "2026-08-06T00:00:00",
        "date_modified": "2026-08-06T00:00:00", "deleted": False,
    } for i, n in enumerate(names)]
    isolated_store.save_files(files)
    back = {f["name"] for f in isolated_store.load_files()}
    assert back == set(names)

def test_content_disposition_is_latin1_safe_for_every_script():

    from routes_streaming import _content_disposition

    for name in ["ホタル.mp4", "中文.zip", "Привет.doc", "ملف.pdf", "קובץ.txt",
                 "ไฟล์.mp4", "हिन्दी.jpg", "Phượng.mkv", "trip 🏖️.jpg"]:
        header = _content_disposition(name)
        header.encode("latin-1")
        assert "filename*=UTF-8''" in header, "the real name must survive"
