import io
import os

import pytest

import app as app_module
import shared
import store
from tests.conftest import isolated_store

@pytest.fixture
def client(isolated_store):
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as client:
        yield client

def _staged_files(store_mod):
    try:
        return sorted(f for f in os.listdir(store_mod.DATA_DIR) if f.startswith(("tgv_upload_", "tgv_dropped_")))
    except OSError:
        return []

def test_new_upload_temp_file_reports_its_real_path(isolated_store):

    path, handle = shared.new_upload_temp_file()
    try:
        assert handle.name == path
        assert os.path.dirname(os.path.abspath(path)) == os.path.abspath(isolated_store.DATA_DIR)
    finally:
        handle.close()
        os.remove(path)

def test_take_uploaded_file_path_adopts_a_staged_file_without_copying(isolated_store):
    path, handle = shared.new_upload_temp_file()
    handle.write(b"payload")

    class _FS:
        stream = handle

    result = shared.take_uploaded_file_path(_FS())

    assert result == path
    assert _staged_files(isolated_store) == [os.path.basename(path)]
    with open(result, "rb") as f:
        assert f.read() == b"payload"

def test_a_different_prefix_is_a_rename_not_a_copy(isolated_store):
    path, handle = shared.new_upload_temp_file()
    handle.write(b"payload")

    class _FS:
        stream = handle

    result = shared.take_uploaded_file_path(_FS(), prefix="tgv_dropped_")

    assert os.path.basename(result).startswith("tgv_dropped_")

    assert _staged_files(isolated_store) == [os.path.basename(result)]
    with open(result, "rb") as f:
        assert f.read() == b"payload"

def test_falls_back_to_copying_a_stream_that_isnt_ours(isolated_store):

    class _FS:
        stream = io.BytesIO(b"foreign")

        def save(self, dst):
            with open(dst, "wb") as f:
                f.write(b"foreign")

    result = shared.take_uploaded_file_path(_FS())

    assert os.path.exists(result)
    with open(result, "rb") as f:
        assert f.read() == b"foreign"

def test_upload_writes_the_body_only_once(client, isolated_store):

    payload = b"x" * (1024 * 1024)
    resp = client.post(
        "/api/uploads/queued/stage",
        data={"file": (io.BytesIO(payload), "probe.bin")},
        content_type="multipart/form-data",
    )

    assert resp.status_code == 200
    staged = resp.get_json()["file_path"]
    assert os.path.getsize(staged) == len(payload)
    with open(staged, "rb") as f:
        assert f.read() == payload

    assert _staged_files(isolated_store) == [os.path.basename(staged)]

def test_a_rejected_upload_leaves_no_orphan(client, isolated_store):

    resp = client.post(
        "/api/files",
        data={"file": (io.BytesIO(b"y" * (1024 * 1024)), "probe.bin"), "folder_id": "does-not-exist"},
        content_type="multipart/form-data",
    )

    assert resp.status_code == 400
    assert _staged_files(isolated_store) == [], "a rejected upload left a full-size orphan behind"

def test_cap_default_is_64_gb(isolated_store):

    assert isolated_store.load_settings()["max_upload_request_bytes"] == 64_000_000_000

def test_cap_can_be_changed_and_applies_live(client, isolated_store):

    resp = client.put(
        "/api/settings/max-upload-request-size",
        json={"max_upload_request_bytes": 8 * 1024 * 1024 * 1024},
    )
    assert resp.status_code == 200
    assert resp.get_json()["max_upload_request_bytes"] == 8 * 1024 * 1024 * 1024
    assert app_module.app.config["MAX_CONTENT_LENGTH"] == 8 * 1024 * 1024 * 1024
    assert isolated_store.load_settings()["max_upload_request_bytes"] == 8 * 1024 * 1024 * 1024

def test_cap_zero_means_no_limit(client, isolated_store):
    resp = client.put("/api/settings/max-upload-request-size", json={"max_upload_request_bytes": 0})
    assert resp.status_code == 200
    assert app_module.app.config["MAX_CONTENT_LENGTH"] is None

def test_cap_rejects_a_value_low_enough_to_break_real_uploads(client, isolated_store):
    resp = client.put("/api/settings/max-upload-request-size", json={"max_upload_request_bytes": 1000})
    assert resp.status_code == 400
    assert "at least 1 GB" in resp.get_json()["error"]

def test_cap_rejects_negative_and_non_numeric(client, isolated_store):
    assert client.put("/api/settings/max-upload-request-size", json={"max_upload_request_bytes": -1}).status_code == 400
    assert client.put("/api/settings/max-upload-request-size", json={"max_upload_request_bytes": "big"}).status_code == 400
