import os

import pytest

import credential_store
import store
from tests.conftest import isolated_store

@pytest.fixture(autouse=True)
def _fake_keyring(monkeypatch):
    fake_store = {}

    def fake_get_password(service, key):
        return fake_store.get((service, key))

    def fake_set_password(service, key, value):
        fake_store[(service, key)] = value

    monkeypatch.setattr(credential_store.keyring, "get_password", fake_get_password)
    monkeypatch.setattr(credential_store.keyring, "set_password", fake_set_password)
    return fake_store

@pytest.fixture(autouse=True)
def _isolated_paths(isolated_store, monkeypatch):

    monkeypatch.setattr(credential_store, "ENCRYPTED_SESSION_PATH", os.path.join(store.DATA_DIR, "telegram_vault.session.enc"))
    monkeypatch.setattr(credential_store, "LEGACY_SESSION_PATH", os.path.join(store.DATA_DIR, "telegram_vault.session"))

def test_load_session_string_returns_none_when_nothing_exists():
    assert credential_store.load_session_string() is None

def test_save_then_load_round_trips():
    credential_store.save_session_string("fake-session-string-data")
    assert credential_store.load_session_string() == "fake-session-string-data"

def test_save_session_string_is_noop_for_empty_string():
    credential_store.save_session_string("")
    assert not os.path.exists(credential_store.ENCRYPTED_SESSION_PATH)
    assert credential_store.load_session_string() is None

def test_encrypted_file_does_not_contain_plaintext_session_string():
    secret = "super-secret-auth-key-material"
    credential_store.save_session_string(secret)
    with open(credential_store.ENCRYPTED_SESSION_PATH, "rb") as f:
        raw = f.read()
    assert secret.encode() not in raw

def test_load_returns_none_for_corrupt_encrypted_file():
    os.makedirs(store.DATA_DIR, exist_ok=True)
    with open(credential_store.ENCRYPTED_SESSION_PATH, "wb") as f:
        f.write(b"not a valid fernet token")
    assert credential_store.load_session_string() is None

def test_reuses_same_key_across_calls(_fake_keyring):

    credential_store.save_session_string("string-one")
    assert len(_fake_keyring) == 1
    key_value = next(iter(_fake_keyring.values()))
    credential_store.save_session_string("string-two")
    assert len(_fake_keyring) == 1
    assert next(iter(_fake_keyring.values())) == key_value
    assert credential_store.load_session_string() == "string-two"
