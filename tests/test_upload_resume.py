import pytest

from tests.conftest import isolated_store

def _pending_upload_fields(**overrides):
    fields = {
        "local_path": "/fake/path/video.mp4", "filename": "video.mp4", "folder_id": None,
        "target_file_id": None, "source": "user", "size_bytes": 100_000_000,
        "max_chunk_size": 1_900_000_000, "telegram_chat_id": "-100123",
        "chunks": [], "skip_duplicate_check": False, "force": False,
        "relative_path": None, "owns_local_path": False,
    }
    fields.update(overrides)
    return fields

def test_save_pending_upload_initializes_part_state_empty(isolated_store):
    isolated_store.save_pending_upload("up1", _pending_upload_fields())
    record = isolated_store.find_pending_upload("up1")
    assert record["upload_file_id"] is None
    assert record["upload_part_size"] is None
    assert record["upload_parts_sent"] == 0

def test_update_pending_upload_part_state_persists(isolated_store):
    isolated_store.save_pending_upload("up1", _pending_upload_fields())
    isolated_store.update_pending_upload_part_state("up1", 123456789012345, 524288, 42)
    record = isolated_store.find_pending_upload("up1")
    assert record["upload_file_id"] == "123456789012345"
    assert record["upload_part_size"] == 524288
    assert record["upload_parts_sent"] == 42

def test_update_pending_upload_part_state_overwrites_previous_value(isolated_store):
    isolated_store.save_pending_upload("up1", _pending_upload_fields())
    isolated_store.update_pending_upload_part_state("up1", 111, 524288, 5)
    isolated_store.update_pending_upload_part_state("up1", 111, 524288, 10)
    record = isolated_store.find_pending_upload("up1")
    assert record["upload_parts_sent"] == 10

def test_update_pending_upload_part_state_survives_in_list_pending_uploads(isolated_store):
    isolated_store.save_pending_upload("up1", _pending_upload_fields())
    isolated_store.update_pending_upload_part_state("up1", 999, 65536, 3)
    records = isolated_store.list_pending_uploads()
    assert len(records) == 1
    assert records[0]["upload_file_id"] == "999"
    assert records[0]["upload_parts_sent"] == 3

def test_part_state_cleared_by_re_saving_pending_upload(isolated_store):

    isolated_store.save_pending_upload("up1", _pending_upload_fields())
    isolated_store.update_pending_upload_part_state("up1", 999, 65536, 3)
    isolated_store.save_pending_upload("up2", _pending_upload_fields())
    record = isolated_store.find_pending_upload("up2")
    assert record["upload_file_id"] is None
    assert record["upload_parts_sent"] == 0
