import inspect

import pytest

import telegram_client
from tests.conftest import isolated_store

CHAT_ID = -1004372805109

def _index_one_file(store, message_id, chat_id=CHAT_ID):
    store.create_file({
        "name": f"f{message_id}.bin",
        "folder_id": None,
        "size_bytes": 10,
        "mime_type": "application/octet-stream",
        "telegram_chat_id": str(chat_id),
        "chunks": [{"message_id": message_id, "size_bytes": 10}],
        "source": "backfill",
    })

def test_is_same_chat_handles_none_without_raising():

    assert telegram_client._is_same_chat(None, CHAT_ID) is False

def test_is_same_chat_matches_across_str_and_int():
    assert telegram_client._is_same_chat(str(CHAT_ID), CHAT_ID) is True
    assert telegram_client._is_same_chat(CHAT_ID, CHAT_ID) is True

def test_is_same_chat_tolerates_garbage():
    assert telegram_client._is_same_chat("not-a-number", CHAT_ID) is False

def test_a_null_telegram_chat_id_cannot_actually_reach_the_index(isolated_store):

    _index_one_file(isolated_store, 800)
    files = isolated_store.load_files()
    files[0]["telegram_chat_id"] = None
    with pytest.raises(Exception) as excinfo:
        isolated_store.save_files(files)
    assert "NOT NULL" in str(excinfo.value)

def test_backfill_tolerates_a_non_numeric_chat_id_in_the_index(isolated_store, monkeypatch):

    _index_one_file(isolated_store, 800)
    isolated_store.save_settings_fields({"archive_chat_id": CHAT_ID})
    files = isolated_store.load_files()
    files[0]["telegram_chat_id"] = "not-a-chat-id"
    isolated_store.save_files(files)

    _, result = _run_backfill(isolated_store, monkeypatch)
    assert result == (0, 0)

def _msg(message_id, text=None):

    from types import SimpleNamespace

    return SimpleNamespace(id=message_id, message=text, file=None, reply_to_msg_id=None)

class _AsyncIter:
    def __init__(self, items):
        self._items = list(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._items:
            raise StopAsyncIteration
        return self._items.pop(0)

class _FakeClient:

    def __init__(self, messages=()):
        self.iter_kwargs = []
        self._messages = list(messages)

    def iter_messages(self, chat_id, **kwargs):
        self.iter_kwargs.append(kwargs)
        return _AsyncIter(self._messages)

    async def get_input_entity(self, chat_id):
        return object()

def _run_backfill(isolated_store, monkeypatch, messages=(), force_full=False):

    import asyncio

    client = _FakeClient(messages)
    monkeypatch.setattr(telegram_client, "_require_client", lambda: client)

    monkeypatch.setattr(telegram_client, "_get_app_data_topic_id", _no_topic)
    monkeypatch.setattr(telegram_client, "run_coro", lambda coro, **kw: asyncio.run(coro))
    result = telegram_client.backfill_scan(force_full=force_full)
    return client, result

async def _no_topic(client, entity):
    return None

def _captured_min_id(isolated_store, monkeypatch, force_full=False):
    client, _ = _run_backfill(isolated_store, monkeypatch, force_full=force_full)
    assert len(client.iter_kwargs) == 1, client.iter_kwargs
    return client.iter_kwargs[0]["min_id"]

def test_min_id_is_zero_not_none_when_index_has_no_matching_files(isolated_store, monkeypatch):

    isolated_store.save_settings_fields({"archive_chat_id": CHAT_ID})

    min_id = _captured_min_id(isolated_store, monkeypatch)

    assert min_id == 0
    assert min_id is not None

def test_none_min_id_really_does_break_telethon():

    from types import SimpleNamespace

    from telethon.client.messages import _MessagesIter

    it = object.__new__(_MessagesIter)
    it.entity = SimpleNamespace(channel_id=1)
    it.reverse = False
    it.last_id = float("inf")
    it.max_id = 0
    it.min_id = None
    with pytest.raises(TypeError):
        it._message_in_range(SimpleNamespace(id=4046))

def test_min_id_ignores_indexed_ids_when_nothing_has_been_scanned(isolated_store, monkeypatch):

    for mid in (794, 2000, 4044):
        _index_one_file(isolated_store, mid)
    isolated_store.save_settings_fields({"archive_chat_id": CHAT_ID})

    assert _captured_min_id(isolated_store, monkeypatch) == 0

def test_min_id_uses_the_persisted_scan_mark(isolated_store, monkeypatch):
    isolated_store.save_settings_fields({
        "archive_chat_id": CHAT_ID,
        "backfill_scanned_chat_id": CHAT_ID,
        "backfill_scanned_up_to_message_id": 4044,
    })

    assert _captured_min_id(isolated_store, monkeypatch) == 4044

def test_scan_mark_is_ignored_when_the_archive_chat_changed(isolated_store, monkeypatch):

    isolated_store.save_settings_fields({
        "archive_chat_id": -100999999,
        "backfill_scanned_chat_id": CHAT_ID,
        "backfill_scanned_up_to_message_id": 4044,
    })

    assert _captured_min_id(isolated_store, monkeypatch) == 0

def test_force_full_ignores_the_scan_mark(isolated_store, monkeypatch):
    isolated_store.save_settings_fields({
        "archive_chat_id": CHAT_ID,
        "backfill_scanned_chat_id": CHAT_ID,
        "backfill_scanned_up_to_message_id": 4044,
    })

    assert _captured_min_id(isolated_store, monkeypatch, force_full=True) == 0

def test_scan_mark_survives_a_str_vs_int_archive_chat_id(isolated_store, monkeypatch):

    isolated_store.save_settings_fields({
        "archive_chat_id": CHAT_ID,
        "backfill_scanned_chat_id": str(CHAT_ID),
        "backfill_scanned_up_to_message_id": 4044,
    })

    assert _captured_min_id(isolated_store, monkeypatch) == 4044

def test_backfill_scan_accepts_force_full_keyword():

    assert "force_full" in inspect.signature(telegram_client.backfill_scan).parameters

def test_completed_scan_records_the_highest_message_it_saw(isolated_store, monkeypatch):
    isolated_store.save_settings_fields({"archive_chat_id": CHAT_ID})

    messages = [_msg(4100), _msg(4090), _msg(3000)]

    _run_backfill(isolated_store, monkeypatch, messages=messages)

    settings = isolated_store.load_settings()
    assert settings["backfill_scanned_up_to_message_id"] == 4100
    assert int(settings["backfill_scanned_chat_id"]) == CHAT_ID

def test_empty_scan_leaves_an_existing_mark_where_it_was(isolated_store, monkeypatch):

    isolated_store.save_settings_fields({
        "archive_chat_id": CHAT_ID,
        "backfill_scanned_chat_id": CHAT_ID,
        "backfill_scanned_up_to_message_id": 4044,
    })

    _run_backfill(isolated_store, monkeypatch, messages=[])

    assert isolated_store.load_settings()["backfill_scanned_up_to_message_id"] == 4044

def test_a_failed_scan_does_not_record_a_mark(isolated_store, monkeypatch):

    isolated_store.save_settings_fields({"archive_chat_id": CHAT_ID})

    class _Exploding(_FakeClient):
        def iter_messages(self, chat_id, **kwargs):
            raise RuntimeError("connection died mid-scan")

    import asyncio

    client = _Exploding()
    monkeypatch.setattr(telegram_client, "_require_client", lambda: client)
    monkeypatch.setattr(telegram_client, "_get_app_data_topic_id", _no_topic)
    monkeypatch.setattr(telegram_client, "run_coro", lambda coro, **kw: asyncio.run(coro))

    with pytest.raises(RuntimeError):
        telegram_client.backfill_scan()

    settings = isolated_store.load_settings()
    assert settings["backfill_scanned_up_to_message_id"] == 0
    assert settings["backfill_scanned_chat_id"] is None

def test_second_run_only_scans_above_the_first_runs_mark(isolated_store, monkeypatch):

    isolated_store.save_settings_fields({"archive_chat_id": CHAT_ID})

    first, _ = _run_backfill(isolated_store, monkeypatch, messages=[_msg(4100)])
    assert first.iter_kwargs[0]["min_id"] == 0

    second, _ = _run_backfill(isolated_store, monkeypatch, messages=[])
    assert second.iter_kwargs[0]["min_id"] == 4100

def test_discard_closes_a_coroutine_that_never_started():
    async def never_run():
        return 1

    coro = never_run()
    assert inspect.getcoroutinestate(coro) == inspect.CORO_CREATED
    telegram_client._discard_coro_if_never_started(coro)
    assert inspect.getcoroutinestate(coro) == inspect.CORO_CLOSED

def test_discard_leaves_a_suspended_coroutine_alone():

    async def suspends():
        await _Never()
        return 1

    class _Never:
        def __await__(self):
            yield

    coro = suspends()
    coro.send(None)
    assert inspect.getcoroutinestate(coro) == inspect.CORO_SUSPENDED
    telegram_client._discard_coro_if_never_started(coro)
    assert inspect.getcoroutinestate(coro) == inspect.CORO_SUSPENDED
    coro.close()

def test_discard_is_a_noop_on_an_already_closed_coroutine():
    async def never_run():
        return 1

    coro = never_run()
    coro.close()
    telegram_client._discard_coro_if_never_started(coro)
    assert inspect.getcoroutinestate(coro) == inspect.CORO_CLOSED
