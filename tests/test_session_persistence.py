from unittest.mock import MagicMock, patch

import pytest

import credential_store
import telegram_client
from tests.conftest import isolated_store

def _client_with_session(session_string):
    client = MagicMock()
    client.session.save.return_value = session_string
    return client

@pytest.fixture(autouse=True)
def _authorized_by_default(monkeypatch):

    monkeypatch.setattr(telegram_client, "_client_authorized", True)

def test_persist_writes_a_new_session(isolated_store):
    telegram_client._persist_client_session(_client_with_session("SESSION-A"))
    assert credential_store.load_session_string() == "SESSION-A"

def test_persist_skips_the_write_when_nothing_changed(isolated_store):
    credential_store.save_session_string("SESSION-A")

    with patch.object(credential_store, "save_session_string") as save:
        telegram_client._persist_client_session(_client_with_session("SESSION-A"))
    save.assert_not_called()

def test_persist_rewrites_when_the_session_changed(isolated_store):

    credential_store.save_session_string("SESSION-OLD-DC")
    telegram_client._persist_client_session(_client_with_session("SESSION-NEW-DC"))
    assert credential_store.load_session_string() == "SESSION-NEW-DC"

def test_persist_recreates_a_session_file_that_vanished(isolated_store):

    credential_store.save_session_string("SESSION-A")
    credential_store.clear_session()
    assert credential_store.load_session_string() is None

    telegram_client._persist_client_session(_client_with_session("SESSION-A"))

    assert credential_store.load_session_string() == "SESSION-A"

def test_persist_ignores_an_empty_session(isolated_store):

    telegram_client._persist_client_session(_client_with_session(""))
    assert credential_store.load_session_string() is None

def test_persist_never_raises(isolated_store):

    broken = MagicMock()
    broken.session.save.side_effect = RuntimeError("boom")
    telegram_client._persist_client_session(broken)

def test_status_reconciles_the_session_when_connected(isolated_store):
    isolated_store.save_settings_fields({"api_id": 1, "api_hash": "h"})
    client = _client_with_session("SESSION-FROM-LIVE-CLIENT")

    with patch.object(telegram_client, "_existing_client", return_value=client), \
         patch.object(telegram_client, "_run_coro_retry_on_lock", return_value=True):
        result = telegram_client.status()

    assert result["connected"] is True
    assert credential_store.load_session_string() == "SESSION-FROM-LIVE-CLIENT"

def test_status_does_not_persist_when_not_connected(isolated_store):

    isolated_store.save_settings_fields({"api_id": 1, "api_hash": "h"})
    client = _client_with_session("SESSION-FROM-UNAUTHORIZED-CLIENT")

    with patch.object(telegram_client, "_existing_client", return_value=client), \
         patch.object(telegram_client, "_run_coro_retry_on_lock", return_value=False):
        result = telegram_client.status()

    assert result["connected"] is False
    assert credential_store.load_session_string() is None

def test_shutdown_persists_before_disconnecting(isolated_store):

    calls = []
    client = _client_with_session("SESSION-AT-SHUTDOWN")

    def record_persist(c):
        calls.append("persist")
        credential_store.save_session_string(c.session.save())

    with patch.object(telegram_client, "_client", client), \
         patch.object(telegram_client, "_loop", None), \
         patch.object(telegram_client, "_persist_client_session", side_effect=record_persist), \
         patch.object(telegram_client, "run_coro", side_effect=lambda *a, **k: calls.append("disconnect")):
        telegram_client.shutdown()

    assert calls == ["persist", "disconnect"]
    assert credential_store.load_session_string() == "SESSION-AT-SHUTDOWN"

def test_persist_refuses_when_authorization_was_never_confirmed(isolated_store, monkeypatch):
    monkeypatch.setattr(telegram_client, "_client_authorized", False)

    telegram_client._persist_client_session(_client_with_session("1BQAN" + "x" * 348))
    assert credential_store.load_session_string() is None

def test_persist_never_overwrites_a_good_session_with_an_unauthorized_one(isolated_store, monkeypatch):

    credential_store.save_session_string("REAL-AUTHORIZED-SESSION")
    monkeypatch.setattr(telegram_client, "_client_authorized", False)

    telegram_client._persist_client_session(_client_with_session("TRANSPORT-ONLY-SESSION"))

    assert credential_store.load_session_string() == "REAL-AUTHORIZED-SESSION"

def test_shutdown_does_not_persist_when_signed_out(isolated_store, monkeypatch):
    monkeypatch.setattr(telegram_client, "_client_authorized", False)
    client = _client_with_session("TRANSPORT-ONLY-SESSION")

    with patch.object(telegram_client, "_client", client), \
         patch.object(telegram_client, "_loop", None), \
         patch.object(telegram_client, "run_coro"):
        telegram_client.shutdown()

    assert credential_store.load_session_string() is None

def test_status_clears_the_flag_when_not_authorized(isolated_store, monkeypatch):

    monkeypatch.setattr(telegram_client, "_client_authorized", True)
    isolated_store.save_settings_fields({"api_id": 1, "api_hash": "h"})

    with patch.object(telegram_client, "_existing_client", return_value=_client_with_session("S")), \
         patch.object(telegram_client, "_run_coro_retry_on_lock", return_value=False):
        telegram_client.status()

    assert telegram_client._client_authorized is False

def test_logout_clears_the_flag(isolated_store, monkeypatch):
    monkeypatch.setattr(telegram_client, "_client_authorized", True)

    with patch.object(telegram_client, "_client", MagicMock()), \
         patch.object(telegram_client, "run_coro", return_value=None):
        telegram_client.logout()

    assert telegram_client._client_authorized is False

def test_a_new_key_over_an_existing_session_is_logged_loudly(isolated_store, monkeypatch, caplog):

    credential_store.save_session_string("SESSION-A")
    monkeypatch.setattr(credential_store.keyring, "get_password", lambda *a: None)
    monkeypatch.setattr(credential_store.keyring, "set_password", lambda *a: None)

    with caplog.at_level("ERROR"):
        credential_store._get_or_create_fernet()

    assert "permanently orphan" in caplog.text

def test_undecryptable_session_is_logged_not_swallowed(isolated_store, monkeypatch, caplog):
    credential_store.save_session_string("SESSION-A")

    monkeypatch.setattr(
        credential_store, "_get_or_create_fernet",
        lambda: credential_store.Fernet(credential_store.Fernet.generate_key()),
    )

    with caplog.at_level("ERROR"):
        assert credential_store.load_session_string() is None

    assert "could not decrypt" in caplog.text

def test_no_spurious_key_warning_on_a_genuine_first_run(isolated_store, monkeypatch, caplog):
    monkeypatch.setattr(credential_store.keyring, "get_password", lambda *a: None)
    monkeypatch.setattr(credential_store.keyring, "set_password", lambda *a: None)

    with caplog.at_level("ERROR"):
        credential_store._get_or_create_fernet()

    assert "permanently orphan" not in caplog.text
