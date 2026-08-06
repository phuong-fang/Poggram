import os
import shutil
import tempfile

import pytest

import credential_store
import store

@pytest.fixture(autouse=True)
def _never_touch_the_real_session(tmp_path, monkeypatch):

    monkeypatch.setattr(credential_store, "ENCRYPTED_SESSION_PATH", str(tmp_path / "telegram_vault.session.enc"))
    monkeypatch.setattr(credential_store, "LEGACY_SESSION_PATH", str(tmp_path / "telegram_vault.session"))

@pytest.fixture
def temp_data_dir(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    cache_dir = data_dir / "cache"
    cache_dir.mkdir()
    return data_dir

@pytest.fixture
def isolated_store(temp_data_dir, monkeypatch):

    monkeypatch.setattr(store, "DATA_DIR", str(temp_data_dir))
    monkeypatch.setattr(store, "CACHE_DIR", str(temp_data_dir / "cache"))
    monkeypatch.setattr(store, "DB_FILE", str(temp_data_dir / "vault.db"))
    monkeypatch.setattr(store, "_INIT_DONE", False)
    return store

@pytest.fixture(autouse=True)
def _reset_status_cache():

    import telegram_client

    telegram_client.invalidate_status_cache()
    yield
    telegram_client.invalidate_status_cache()
