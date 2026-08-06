import time
from unittest.mock import MagicMock

import pytest

import telegram_client
from tests.conftest import isolated_store

@pytest.fixture(autouse=True)
def _clean_cache():
    telegram_client.invalidate_status_cache()
    yield
    telegram_client.invalidate_status_cache()

@pytest.fixture
def fake_client(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(telegram_client, "_existing_client", lambda: client)
    return client

def _count_checks(monkeypatch, result=True, raises=None):
    calls = []

    def _fake(coro_factory, **kwargs):
        calls.append(1)
        if raises is not None:
            raise raises
        return result

    monkeypatch.setattr(telegram_client, "_run_coro_retry_on_lock", _fake)
    monkeypatch.setattr(telegram_client, "_persist_client_session", lambda c: None)
    return calls

def test_repeated_calls_hit_telegram_once(monkeypatch, fake_client, isolated_store):

    calls = _count_checks(monkeypatch)
    for _ in range(5):
        assert telegram_client.status()["connected"] is True
    assert len(calls) == 1, f"{len(calls)} RPCs for 5 status calls"

def test_cache_expires(monkeypatch, fake_client, isolated_store):
    calls = _count_checks(monkeypatch)
    telegram_client.status()
    monkeypatch.setattr(telegram_client, "_STATUS_CACHE_TTL_SECONDS", 0.0)
    telegram_client.status()
    assert len(calls) == 2, "an expired cache must re-check"

def test_a_failed_check_does_not_report_signed_out(monkeypatch, fake_client, isolated_store):

    _count_checks(monkeypatch, result=True)
    assert telegram_client.status()["connected"] is True

    monkeypatch.setattr(telegram_client, "_STATUS_CACHE_TTL_SECONDS", 0.0)
    _count_checks(monkeypatch, raises=TimeoutError("lock busy"))
    assert telegram_client.status()["connected"] is True, (
        "a busy lock was reported as a signed-out account"
    )

def test_failure_with_no_prior_answer_is_false(monkeypatch, fake_client, isolated_store):

    _count_checks(monkeypatch, raises=TimeoutError("lock busy"))
    assert telegram_client.status()["connected"] is False

def test_logout_invalidates_the_cache(monkeypatch, fake_client, isolated_store):

    calls = _count_checks(monkeypatch, result=True)
    telegram_client.status()
    telegram_client.invalidate_status_cache()
    telegram_client.status()
    assert len(calls) == 2, "the cache survived a logout"

def test_disconnect_is_cached_too_and_does_not_flip_back(monkeypatch, fake_client, isolated_store):
    calls = _count_checks(monkeypatch, result=False)
    assert telegram_client.status()["connected"] is False
    assert telegram_client.status()["connected"] is False
    assert len(calls) == 1

def test_forum_check_hits_telegram_once(monkeypatch, isolated_store):

    telegram_client.invalidate_forum_cache()
    isolated_store.save_settings_fields({"archive_chat_id": -100})
    calls = []

    def _fake(factory, **kw):
        calls.append(1)
        return True

    monkeypatch.setattr(telegram_client, "_require_client", lambda: MagicMock())
    monkeypatch.setattr(telegram_client, "_run_coro_retry_on_lock", _fake)

    for _ in range(5):
        assert telegram_client.is_forum_enabled() is True
    assert len(calls) == 1, f"{len(calls)} round trips for 5 checks"

def test_forum_cache_is_keyed_by_chat(monkeypatch, isolated_store):

    telegram_client.invalidate_forum_cache()
    isolated_store.save_settings_fields({"archive_chat_id": -100})
    answers = iter([True, False])
    monkeypatch.setattr(telegram_client, "_require_client", lambda: MagicMock())
    monkeypatch.setattr(telegram_client, "_run_coro_retry_on_lock",
                        lambda factory, **kw: next(answers))

    assert telegram_client.is_forum_enabled() is True
    isolated_store.save_settings_fields({"archive_chat_id": -200})
    assert telegram_client.is_forum_enabled() is False

def test_toggling_forum_mode_invalidates_the_cache(monkeypatch, isolated_store):
    telegram_client.invalidate_forum_cache()
    isolated_store.save_settings_fields({"archive_chat_id": -100})
    monkeypatch.setattr(telegram_client, "_require_client", lambda: MagicMock())
    monkeypatch.setattr(telegram_client, "_run_coro_retry_on_lock", lambda factory, **kw: True)
    assert telegram_client.is_forum_enabled() is True

    telegram_client.invalidate_forum_cache()
    monkeypatch.setattr(telegram_client, "_run_coro_retry_on_lock", lambda factory, **kw: False)
    assert telegram_client.is_forum_enabled() is False, "stale answer after a toggle"
