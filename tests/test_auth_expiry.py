from unittest.mock import MagicMock

import pytest

import telegram_client
from tests.conftest import isolated_store

def _client(authorized):
    client = MagicMock()
    client.is_connected.return_value = True

    async def _auth():
        return authorized

    client.is_user_authorized = _auth
    return client

@pytest.fixture
def run_inline(monkeypatch):

    import asyncio

    monkeypatch.setattr(telegram_client, "_run_coro_retry_on_lock",
                        lambda factory, **kw: asyncio.run(factory()))

def test_expired_session_says_so(monkeypatch, run_inline, isolated_store):
    isolated_store.save_settings_fields({"api_id": 123, "api_hash": "h", "phone_number": "+100"})
    monkeypatch.setattr(telegram_client, "_existing_client", lambda: _client(False))

    with pytest.raises(ValueError) as err:
        telegram_client._require_client()
    message = str(err.value)
    assert "no longer valid" in message, message
    assert "set it up in Settings first" not in message, (
        "a configured install was told it had never been set up"
    )

def test_never_configured_still_gets_the_setup_message(monkeypatch, run_inline, isolated_store):
    monkeypatch.setattr(telegram_client, "_existing_client", lambda: _client(False))

    with pytest.raises(ValueError) as err:
        telegram_client._require_client()
    assert "set it up in Settings first" in str(err.value)

def test_expiry_clears_the_cached_connected_state(monkeypatch, run_inline, isolated_store):

    isolated_store.save_settings_fields({"api_id": 123, "api_hash": "h", "phone_number": "+100"})
    telegram_client._status_cache_put(True)
    monkeypatch.setattr(telegram_client, "_client_authorized", True)
    monkeypatch.setattr(telegram_client, "_existing_client", lambda: _client(False))

    with pytest.raises(ValueError):
        telegram_client._require_client()

    assert telegram_client._status_cache_get() is None, "stale 'connected' survived"
    assert telegram_client._client_authorized is False

def test_authorized_client_is_returned_untouched(monkeypatch, run_inline, isolated_store):
    client = _client(True)
    monkeypatch.setattr(telegram_client, "_existing_client", lambda: client)
    assert telegram_client._require_client() is client
