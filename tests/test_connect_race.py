import threading
from unittest.mock import MagicMock

import pytest

import telegram_client
from tests.conftest import isolated_store

@pytest.fixture(autouse=True)
def _reset_client_state(monkeypatch):
    monkeypatch.setattr(telegram_client, "_client", None, raising=False)
    monkeypatch.setattr(telegram_client, "_pending_client", None, raising=False)
    yield

@pytest.fixture
def fake_construction(monkeypatch):

    built = []

    def _factory(*args, **kwargs):
        c = MagicMock(name=f"client{len(built)}")
        c.client_index = len(built)
        built.append(c)
        return c

    monkeypatch.setattr(telegram_client, "TelegramClient", _factory)
    monkeypatch.setattr(telegram_client, "_raise_session_busy_timeout", lambda c: None)
    monkeypatch.setattr(telegram_client, "_load_client_session", lambda: "session")
    return built

def test_connect_pins_the_client_it_sent_the_code_from(fake_construction, monkeypatch, isolated_store):

    monkeypatch.setattr(telegram_client, "run_coro", lambda coro, **kw: "code-hash-abc")
    telegram_client.connect(123, "hash", "+100")

    pinned = telegram_client._pending_client
    assert pinned is not None
    assert telegram_client._client is pinned

    other = MagicMock(name="interloper")
    monkeypatch.setattr(telegram_client, "_client", other)

    signed_in_on = {}

    def _capture(coro, **kw):

        coro.close()
        signed_in_on["client"] = telegram_client._pending_client or telegram_client._client
        return "connected"

    monkeypatch.setattr(telegram_client, "run_coro", _capture)
    monkeypatch.setattr(telegram_client, "_finish_auth", lambda: None)
    telegram_client.submit_code("11111")

    assert signed_in_on["client"] is pinned, (
        "sign-in was directed at a client that never sent the login code"
    )

def test_concurrent_connect_and_existing_client_build_one_survivor(fake_construction, monkeypatch, isolated_store):

    isolated_store.save_settings_fields({"api_id": 123, "api_hash": "hash"})
    monkeypatch.setattr(telegram_client, "run_coro", lambda coro, **kw: "code-hash-abc")

    barrier = threading.Barrier(2)
    errors = []

    def _connect():
        try:
            barrier.wait(timeout=5)
            telegram_client.connect(123, "hash", "+100")
        except Exception as e:
            errors.append(e)

    def _existing():
        try:
            barrier.wait(timeout=5)
            telegram_client._existing_client()
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=_connect), threading.Thread(target=_existing)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors, errors
    assert telegram_client._client is not None

    installed = telegram_client._client
    for c in fake_construction:
        if c is not installed:
            assert c.disconnect.called, (
                "a replaced client was left connected - this is how orphaned "
                "senders kept writing underneath the app"
            )

def test_logout_drops_the_pinned_client(fake_construction, monkeypatch, isolated_store):
    monkeypatch.setattr(telegram_client, "run_coro", lambda coro, **kw: "code-hash-abc")
    telegram_client.connect(123, "hash", "+100")
    assert telegram_client._pending_client is not None

    monkeypatch.setattr(telegram_client, "run_coro", lambda coro, **kw: None)
    monkeypatch.setattr(telegram_client, "_persist_client_session", lambda c: None)
    telegram_client.logout()
    assert telegram_client._pending_client is None
