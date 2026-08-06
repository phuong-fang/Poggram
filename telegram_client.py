import asyncio
import concurrent.futures
import hashlib
import inspect
import io
import logging
import math
import mimetypes
import os
import random
import re
import sqlite3
import threading
import time

from telethon import TelegramClient, custom, functions, helpers as telethon_helpers, types, utils as telethon_utils
from telethon.errors import (
    ChannelForumMissingError, PhoneCodeExpiredError, PhoneCodeInvalidError, SessionPasswordNeededError,
)
from telethon.sessions import StringSession
from telethon.tl.functions.channels import CreateChannelRequest, ToggleForumRequest
from telethon.tl.functions.messages import CreateForumTopicRequest, ForwardMessagesRequest, GetForumTopicsRequest
from telethon.tl.types import DocumentAttributeFilename, PeerChannel, PeerChat, PeerUser

import credential_store
import store

logger = logging.getLogger(__name__)

def _chat_id_to_peer(chat_id):

    chat_id = int(chat_id)
    if chat_id > 0:
        return types.PeerUser(chat_id)
    elif chat_id < -1000000000000:

        return types.PeerChannel(abs(chat_id) - 1000000000000)
    else:

        return types.PeerChat(abs(chat_id))

def _load_client_session():
    return StringSession(credential_store.load_session_string() or None)

def _persist_client_session(client):

    if not _client_authorized:
        return
    try:
        session_string = client.session.save()
        if not session_string:
            return
        if session_string == credential_store.load_session_string():
            return
        credential_store.save_session_string(session_string)
    except Exception:
        logger.exception("Failed to persist Telegram session to disk - next restart will require re-login")

TRANSFER_TIMEOUT = 14400

BACKFILL_TIMEOUT = 300

FLOOD_SLEEP_THRESHOLD = 1800

DOWNLOAD_PARALLEL_WORKERS = 3

_loop = None
_thread = None
_client = None

_client_authorized = False

_pending_client = None

_STATUS_CACHE_TTL_SECONDS = 10.0
_status_cache_value = None
_status_cache_at = 0.0
_status_cache_lock = threading.Lock()

def _status_cache_get():

    with _status_cache_lock:
        if _status_cache_value is None:
            return None
        if (time.monotonic() - _status_cache_at) >= _STATUS_CACHE_TTL_SECONDS:
            return None
        return _status_cache_value

def _status_cache_last():

    with _status_cache_lock:
        return _status_cache_value

def _status_cache_put(connected):
    global _status_cache_value, _status_cache_at
    with _status_cache_lock:
        _status_cache_value = connected
        _status_cache_at = time.monotonic()

def invalidate_status_cache():

    global _status_cache_value, _status_cache_at
    with _status_cache_lock:
        _status_cache_value = None
        _status_cache_at = 0.0

_client_init_lock = threading.Lock()

_telethon_lock = None
_telethon_lock_state = {"held": False, "foreground_waiting": 0}

_last_foreground_activity_time = 0.0

_pending_phone = None
_pending_phone_code_hash = None

def start():

    global _loop, _thread
    _loop = asyncio.new_event_loop()

    def _run():
        asyncio.set_event_loop(_loop)
        _loop.run_forever()

    _thread = threading.Thread(target=_run, daemon=True)
    _thread.start()

    _start_connection_health_check()

def _start_connection_health_check():

    import logging
    logger = logging.getLogger(__name__)

    async def _health_check():
        while True:
            try:
                await asyncio.sleep(60)
                client = _existing_client()
                if client is not None:

                    if not client.is_connected():
                        logger.info("Connection health check: reconnecting stale Telegram connection")
                        try:
                            await asyncio.wait_for(client.connect(), timeout=10)
                            logger.info("Connection health check: reconnection successful")
                        except Exception as e:
                            logger.warning(f"Connection health check: reconnection failed: {e}")
            except Exception as e:
                logger.warning(f"Connection health check: error: {e}")

    def _run_health_check():
        asyncio.run_coroutine_threadsafe(_health_check(), _loop)

    threading.Thread(target=_run_health_check, daemon=True).start()

class UploadCancelled(Exception):

    pass

class CancelToken:

    def __init__(self):
        self._lock = threading.Lock()
        self._future = None
        self._cancelled = False
        self._forget = False

    def attach(self, future):
        with self._lock:
            if self._cancelled:
                future.cancel()
            self._future = future

    def detach(self):
        with self._lock:
            self._future = None

    def cancel(self, forget=False):

        with self._lock:
            self._cancelled = True
            if forget:
                self._forget = True
            if self._future is not None:
                self._future.cancel()

    def is_cancelled(self):
        with self._lock:
            return self._cancelled

    def should_forget(self):
        with self._lock:
            return self._forget

async def _with_telethon_lock(coro, priority="foreground"):

    global _telethon_lock
    if _telethon_lock is None:
        _telethon_lock = asyncio.Condition()
    global _last_foreground_activity_time
    async with _telethon_lock:
        if priority == "background":
            while _telethon_lock_state["held"] or _telethon_lock_state["foreground_waiting"] > 0:
                await _telethon_lock.wait()
            _telethon_lock_state["held"] = True
        else:
            _last_foreground_activity_time = time.time()
            _telethon_lock_state["foreground_waiting"] += 1
            try:
                while _telethon_lock_state["held"]:
                    await _telethon_lock.wait()
            finally:
                _telethon_lock_state["foreground_waiting"] -= 1
            _telethon_lock_state["held"] = True
    try:
        return await coro
    finally:
        async with _telethon_lock:
            _telethon_lock_state["held"] = False
            _telethon_lock.notify_all()

FOREGROUND_RECENCY_WINDOW_SECONDS = 3.0

def foreground_recently_active(window_seconds=FOREGROUND_RECENCY_WINDOW_SECONDS):

    return (time.time() - _last_foreground_activity_time) < window_seconds

def _discard_coro_if_never_started(coro):

    try:
        if inspect.getcoroutinestate(coro) == inspect.CORO_CREATED:
            coro.close()
    except Exception:
        pass

def run_coro(coro, timeout=60, priority="foreground"):

    future = asyncio.run_coroutine_threadsafe(_with_telethon_lock(coro, priority), _loop)
    try:
        return future.result(timeout=timeout)
    except TimeoutError:
        future.cancel()
        raise TimeoutError(f"Timed out after {timeout}s waiting for Telegram - the connection may be too slow for this transfer size.")

def _run_coro_retry_on_lock(coro_factory, timeout=30, attempts=8, delay=0.4, priority="foreground"):

    last_error = None
    for attempt in range(attempts):
        coro = coro_factory()
        try:
            return run_coro(coro, timeout=timeout, priority=priority)
        except sqlite3.OperationalError as e:
            _discard_coro_if_never_started(coro)
            if "locked" not in str(e).lower() or attempt == attempts - 1:
                raise
            last_error = e
            time.sleep(delay + random.uniform(0, delay))
        except TimeoutError as e:
            _discard_coro_if_never_started(coro)
            if attempt == attempts - 1:
                raise
            last_error = e
    raise last_error

def run_coro_cancellable(coro_factory, cancel_token, timeout=60, priority="foreground", manages_own_lock=False):

    if cancel_token is not None and cancel_token.is_cancelled():
        raise UploadCancelled()
    coro = coro_factory()
    scheduled = coro if manages_own_lock else _with_telethon_lock(coro, priority)
    future = asyncio.run_coroutine_threadsafe(scheduled, _loop)
    if cancel_token is not None:
        cancel_token.attach(future)
    try:
        return future.result(timeout=timeout)
    except concurrent.futures.CancelledError:
        raise UploadCancelled()
    except TimeoutError:
        future.cancel()
        raise TimeoutError(f"Timed out after {timeout}s waiting for Telegram - the connection may be too slow for this transfer size.")
    finally:
        if cancel_token is not None:
            cancel_token.detach()

def shutdown():
    if _client is not None:

        _persist_client_session(_client)
        try:
            run_coro(_client.disconnect(), timeout=10)
        except Exception:
            pass
    if _loop is not None:
        _loop.call_soon_threadsafe(_loop.stop)

def _raise_session_busy_timeout(client):

    conn = getattr(client.session, "_conn", None)
    if conn is not None:
        conn.execute("PRAGMA busy_timeout = 30000")

def _existing_client():

    global _client
    if _client is not None:
        return _client
    with _client_init_lock:
        if _client is not None:
            return _client
        settings = store.load_settings()
        api_id, api_hash = settings.get("api_id"), settings.get("api_hash")
        if not api_id or not api_hash:
            return None
        _client = TelegramClient(
            _load_client_session(), int(api_id), api_hash, loop=_loop, flood_sleep_threshold=FLOOD_SLEEP_THRESHOLD
        )
        _raise_session_busy_timeout(_client)
        return _client

def status():

    global _client_authorized
    settings = store.load_settings()
    client = _existing_client()
    connected = False
    if client is not None:
        async def _check():
            if not client.is_connected():

                try:
                    await asyncio.wait_for(client.connect(), timeout=15)
                except Exception:
                    return False
            return await client.is_user_authorized()

        cached = _status_cache_get()
        if cached is not None:
            connected = cached
        else:
            try:
                connected = _run_coro_retry_on_lock(_check, timeout=15)
                _status_cache_put(connected)
            except Exception:

                last = _status_cache_last()
                connected = last if last is not None else False
                logger.debug("Status check failed - reusing last known connected=%s", connected)

        _client_authorized = connected
        if connected:

            _persist_client_session(client)
    return {
        "connected": connected,
        "phone_number": settings.get("phone_number"),
        "archive_chat_id": settings.get("archive_chat_id"),
        "archive_chat_title": settings.get("archive_chat_title"),
        "is_premium": settings.get("is_premium"),
        "max_chunk_size_bytes": settings.get("max_chunk_size_bytes"),
    }

def connect(api_id, api_hash, phone_number):

    global _client, _pending_client, _pending_phone, _pending_phone_code_hash
    try:
        api_id = int(api_id)
    except (TypeError, ValueError):
        raise ValueError("API ID should be a number - check my.telegram.org and try again.")

    store.save_settings_fields({"api_id": api_id, "api_hash": api_hash, "phone_number": phone_number})
    with _client_init_lock:
        replaced = _client
        _client = TelegramClient(
            _load_client_session(), api_id, api_hash, loop=_loop, flood_sleep_threshold=FLOOD_SLEEP_THRESHOLD
        )
        _raise_session_busy_timeout(_client)
        _pending_client = _client
        client = _client

    if replaced is not None and replaced is not client:
        try:
            run_coro(replaced.disconnect(), timeout=10)
        except Exception:
            logger.debug("Couldn't disconnect the replaced client", exc_info=True)

    async def _do():
        await client.connect()
        result = await client.send_code_request(phone_number)
        return result.phone_code_hash

    _pending_phone_code_hash = run_coro(_do())
    _pending_phone = phone_number

def submit_code(code):

    client = _pending_client or _client

    async def _do():
        try:
            await client.sign_in(_pending_phone, code, phone_code_hash=_pending_phone_code_hash)
            return "connected"
        except SessionPasswordNeededError:
            return "password"
        except PhoneCodeInvalidError:
            raise ValueError("That code doesn't match what Telegram sent - check it and try again.")
        except PhoneCodeExpiredError:
            raise ValueError("That code expired - go back and reconnect to request a new one.")

    step = run_coro(_do())
    if step == "connected":
        _finish_auth()
    return step

def submit_password(password):
    client = _pending_client or _client

    async def _do():
        await client.sign_in(password=password)

    run_coro(_do())
    _finish_auth()

def refresh_premium_status():

    client = _require_client()

    async def _do():
        me = await client.get_me()
        return bool(getattr(me, "premium", False))

    is_premium = run_coro(_do())
    settings = store.load_settings()
    current_chunk = settings.get("max_chunk_size_bytes") or 1_900_000_000
    new_chunk = 3_900_000_000 if is_premium else 1_900_000_000
    updates = {"is_premium": is_premium}

    if current_chunk in (1_900_000_000, 3_900_000_000):
        updates["max_chunk_size_bytes"] = new_chunk
    store.save_settings_fields(updates)
    return is_premium

def logout():

    global _client, _client_authorized, _pending_client
    if _client is not None:
        async def _do_logout():
            try:
                await _client.log_out()
            except Exception:
                pass

        try:
            run_coro(_do_logout(), timeout=15)
        except Exception:
            pass
        try:
            run_coro(_client.disconnect(), timeout=10)
        except Exception:
            pass
        _client = None

    _client_authorized = False
    _pending_client = None

    invalidate_status_cache()
    credential_store.clear_session()
    store.save_settings_fields({
        "archive_chat_id": None,
        "archive_chat_title": None,
        "is_premium": False,
        "app_data_backup_last_known_message_id": None,
    })

def _finish_auth():

    global _client_authorized, _pending_client

    client = _pending_client or _client

    async def _do():
        me = await client.get_me()
        return bool(getattr(me, "premium", False))

    is_premium = run_coro(_do())
    max_chunk = 3_900_000_000 if is_premium else 1_900_000_000
    store.save_settings_fields({"is_premium": is_premium, "max_chunk_size_bytes": max_chunk})

    _client_authorized = True
    invalidate_status_cache()
    _persist_client_session(client)

    _pending_client = None

def scan_archive_candidates():

    client = _require_client()
    async def _do():
        candidates = []
        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            if hasattr(entity, "megagroup") and entity.megagroup:
                participants = getattr(entity, "participants_count", 0)

                chat_id = entity.id
                if hasattr(entity, "megagroup") and entity.megagroup:
                    chat_id = int(f"-100{abs(chat_id)}")
                candidates.append({
                    "id": chat_id,
                    "title": dialog.name or "Unnamed",
                    "participant_count": participants,
                })
        return candidates
    try:
        return run_coro(_do(), timeout=60)
    except Exception as e:
        return {"error": str(e) or type(e).__name__}

def create_archive_supergroup(title):

    title = (title or "").strip() or "Poggram Archive"

    async def _do():
        result = await _client(CreateChannelRequest(
            title=title,
            about="Poggram archive - managed by the Poggram app. Files saved through the app land here.",
            megagroup=True,
        ))
        chat = result.chats[0]
        return telethon_utils.get_peer_id(chat), chat.title

    chat_id, chat_title = run_coro(_do())
    store.save_settings_fields({"archive_chat_id": chat_id, "archive_chat_title": chat_title})
    return chat_id, chat_title

def _require_client():
    client = _existing_client()
    if client is None:
        raise ValueError("Telegram isn't connected yet - set it up in Settings first.")

    async def _ensure():
        if not client.is_connected():
            import logging
            logger = logging.getLogger(__name__)
            logger.info("Reconnecting stale Telegram connection on-demand")

            try:
                await asyncio.wait_for(client.connect(), timeout=15)
                logger.info("On-demand reconnection successful")
            except asyncio.TimeoutError:
                raise ValueError("Telegram connection timed out - the network may be unavailable.")
            except Exception as e:
                raise ValueError(f"Telegram connection failed: {e}")
        if not await client.is_user_authorized():

            global _client_authorized
            _client_authorized = False

            invalidate_status_cache()
            settings = store.load_settings()
            if settings.get("api_id") and settings.get("phone_number"):
                raise ValueError(
                    "Your Telegram session is no longer valid - it may have expired or been "
                    "signed out from another device. Reconnect in Settings."
                )
            raise ValueError("Telegram isn't connected yet - set it up in Settings first.")

    _run_coro_retry_on_lock(lambda: _ensure(), timeout=60)
    return client

def require_archive_chat():
    chat_id = store.load_settings().get("archive_chat_id")
    if not chat_id:
        raise ValueError("Create an archive group in Settings first.")
    return chat_id

def compute_content_hash(file_path):

    hasher = hashlib.blake2b(digest_size=8)
    with open(file_path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()

def upload_file(
    file_path, filename, max_chunk_size, on_progress=None, cancel_token=None, content_hash=None, thumb_bytes=None,
    reply_to=None, priority="foreground", on_chunk_done=None, resume_chunks=None,
):

    client = _require_client()
    chat_id = require_archive_chat()
    total_size = os.path.getsize(file_path)

    if total_size <= max_chunk_size:

        def _tg_progress(sent, total):
            if cancel_token is not None and cancel_token.is_cancelled():
                raise UploadCancelled()
            if on_progress:
                on_progress(1 if sent >= total else 0, 1, sent)

        async def _do_single():
            kwargs = {}
            if thumb_bytes is not None:
                kwargs["thumb"] = thumb_bytes
            if reply_to is not None:
                kwargs["reply_to"] = reply_to
            message = await _with_telethon_lock(
                client.send_file(
                    chat_id, file=file_path, attributes=[DocumentAttributeFilename(filename)],
                    force_document=True, progress_callback=_tg_progress, **kwargs,
                ),
                priority,
            )
            return message.id

        message_id = run_coro_cancellable(_do_single, cancel_token, timeout=TRANSFER_TIMEOUT, priority=priority, manages_own_lock=True)
        if on_progress:
            on_progress(1, 1, total_size)
        return chat_id, [{"message_id": message_id, "size_bytes": total_size}]

    n_chunks = math.ceil(total_size / max_chunk_size)
    base_name, ext = os.path.splitext(filename)

    file_tag = content_hash if content_hash is not None else compute_content_hash(file_path)

    chunks = list(resume_chunks) if resume_chunks else []
    bytes_done_before = sum(c["size_bytes"] for c in chunks)
    resume_from = len(chunks)
    if on_progress and resume_from:
        on_progress(resume_from, n_chunks, bytes_done_before)

    with open(file_path, "rb") as f:
        if bytes_done_before:
            f.seek(bytes_done_before)
        for i in range(resume_from, n_chunks):
            if cancel_token is not None and cancel_token.is_cancelled():
                raise UploadCancelled()
            data = f.read(max_chunk_size)
            part_name = f"{base_name}.{file_tag}.part{i + 1:02d}of{n_chunks:02d}{ext}"

            def _tg_progress(sent, total, i=i, bytes_done_before=bytes_done_before):
                if cancel_token is not None and cancel_token.is_cancelled():
                    raise UploadCancelled()
                if on_progress:
                    on_progress(i, n_chunks, bytes_done_before + sent)

            async def _do_chunk(data=data, part_name=part_name, _tg_progress=_tg_progress, i=i):
                kwargs = {}

                if i == 0 and thumb_bytes is not None:
                    kwargs["thumb"] = thumb_bytes

                if reply_to is not None:
                    kwargs["reply_to"] = reply_to
                message = await _with_telethon_lock(
                    client.send_file(
                        chat_id, file=io.BytesIO(data), attributes=[DocumentAttributeFilename(part_name)],
                        force_document=True, progress_callback=_tg_progress, **kwargs,
                    ),
                    priority,
                )
                return message.id

            message_id = run_coro_cancellable(_do_chunk, cancel_token, timeout=TRANSFER_TIMEOUT, priority=priority, manages_own_lock=True)
            chunks.append({"message_id": message_id, "size_bytes": len(data)})
            bytes_done_before += len(data)
            if on_chunk_done:
                on_chunk_done(list(chunks))
            if on_progress:
                on_progress(i + 1, n_chunks, bytes_done_before)

    return chat_id, chunks

UPLOAD_PARALLEL_WORKERS = 3

BACKGROUND_BACKOFF_WORKERS = 1

def _background_backoff_workers():
    try:
        return max(1, int(store.load_settings().get("sync_backoff_workers", BACKGROUND_BACKOFF_WORKERS)))
    except (TypeError, ValueError):
        return BACKGROUND_BACKOFF_WORKERS

def _select_part_size(total_size, requested_kb, is_premium):

    max_parts = 8000 if is_premium else 4000
    if requested_kb <= 0:
        if total_size <= 100 * 1024 * 1024:
            requested_kb = 64
        elif total_size <= 750 * 1024 * 1024:
            requested_kb = 256
        else:
            requested_kb = 512
    requested_kb = min(requested_kb, 512)
    while requested_kb < 512 and math.ceil(total_size / (requested_kb * 1024)) > max_parts:
        requested_kb *= 2
    part_size_bytes = requested_kb * 1024
    if math.ceil(total_size / part_size_bytes) > max_parts:
        return None
    return part_size_bytes

def upload_file_parallel(
    file_path, filename, max_chunk_size, on_progress=None, cancel_token=None, content_hash=None, thumb_bytes=None,
    reply_to=None, num_workers=UPLOAD_PARALLEL_WORKERS, part_size_kb=0, priority="foreground",
    on_chunk_done=None, resume_chunks=None, resume_part_state=None, on_part_done=None,
):

    if num_workers <= 1:
        return upload_file(
            file_path, filename, max_chunk_size, on_progress=on_progress, cancel_token=cancel_token,
            content_hash=content_hash, thumb_bytes=thumb_bytes, reply_to=reply_to,
            on_chunk_done=on_chunk_done, resume_chunks=resume_chunks,
        )
    client = _require_client()
    chat_id = require_archive_chat()
    total_size = os.path.getsize(file_path)

    if total_size <= max_chunk_size:

        def _tg_progress(sent, total):
            if cancel_token is not None and cancel_token.is_cancelled():
                raise UploadCancelled()
            if on_progress:
                on_progress(1 if sent >= total else 0, 1, sent)

        message_id = run_coro_cancellable(
            lambda: _do_parallel_upload(
                client, chat_id, file_path, filename, total_size, part_size_kb, num_workers, _tg_progress,
                cancel_token, thumb_bytes, reply_to, priority,
                resume_part_state=resume_part_state, on_part_done=on_part_done,
            ),
            cancel_token, timeout=TRANSFER_TIMEOUT, manages_own_lock=True,
        )
        return chat_id, [{"message_id": message_id, "size_bytes": total_size}]

    n_chunks = math.ceil(total_size / max_chunk_size)
    base_name, ext = os.path.splitext(filename)
    file_tag = content_hash if content_hash is not None else compute_content_hash(file_path)

    chunks = list(resume_chunks) if resume_chunks else []
    bytes_done_before = sum(c["size_bytes"] for c in chunks)
    resume_from = len(chunks)
    if on_progress and resume_from:
        on_progress(resume_from, n_chunks, bytes_done_before)
    with open(file_path, "rb") as f:
        if bytes_done_before:
            f.seek(bytes_done_before)
        for i in range(resume_from, n_chunks):
            if cancel_token is not None and cancel_token.is_cancelled():
                raise UploadCancelled()
            data = f.read(max_chunk_size)
            part_name = f"{base_name}.{file_tag}.part{i + 1:02d}of{n_chunks:02d}{ext}"

            def _tg_progress(sent, total, i=i, bytes_done_before=bytes_done_before):
                if cancel_token is not None and cancel_token.is_cancelled():
                    raise UploadCancelled()
                if on_progress:
                    on_progress(i, n_chunks, bytes_done_before + sent)

            message_id = run_coro_cancellable(
                lambda: _do_parallel_upload(
                    client, chat_id, io.BytesIO(data), part_name, len(data), part_size_kb, num_workers,
                    _tg_progress, cancel_token,
                    thumb_bytes if i == 0 else None, reply_to, priority,
                    resume_part_state=resume_part_state if i == resume_from else None,
                    on_part_done=on_part_done,
                ),
                cancel_token, timeout=TRANSFER_TIMEOUT, manages_own_lock=True,
            )
            chunks.append({"message_id": message_id, "size_bytes": len(data)})
            bytes_done_before += len(data)
            if on_chunk_done:
                on_chunk_done(list(chunks))
            if on_progress:
                on_progress(i + 1, n_chunks, bytes_done_before)

    return chat_id, chunks

def _is_missing_part_error(error):

    text = str(error).upper()
    return "FILE_PART" in text and "MISSING" in text or "MISSING FROM STORAGE" in text

async def _do_parallel_upload(
    client, chat_id, file_input, filename, file_size, part_size_kb, num_workers, on_progress_chunk, cancel_token,
    thumb_bytes, reply_to, priority="foreground", resume_part_state=None, on_part_done=None,
):

    is_premium = bool(store.load_settings().get("is_premium", False))
    if resume_part_state and resume_part_state.get("part_size"):

        part_size = resume_part_state["part_size"]
    else:
        part_size = _select_part_size(file_size, part_size_kb, is_premium)
    if part_size is None:

        raise ValueError(
            f"Chunk too large for the protocol's part cap: {file_size} bytes at 512KB parts "
            f"exceeds the {8000 if is_premium else 4000}-part limit"
        )

    if isinstance(file_input, str):
        stream = open(file_input, "rb")
        own_stream = True
    else:
        stream = file_input
        own_stream = False
    try:
        is_big = file_size > 10 * 1024 * 1024
        part_count = (file_size + part_size - 1) // part_size
        if resume_part_state and resume_part_state.get("file_id") is not None:

            file_id = int(resume_part_state["file_id"])
            sent_count = min(int(resume_part_state.get("parts_sent") or 0), part_count)

            resumed_attempt = True
        else:

            file_id = int.from_bytes(os.urandom(8), signed=True, byteorder="little")
            sent_count = 0
            resumed_attempt = False

        restarted_fresh = False

        md5 = hashlib.md5() if not is_big else None
        if md5 is not None and sent_count:

            stream.seek(0)
            remaining = sent_count * part_size
            while remaining:
                block = stream.read(min(remaining, 1024 * 1024))
                if not block:
                    break
                md5.update(block)
                remaining -= len(block)
            stream.seek(0)

        if on_progress_chunk and sent_count:
            on_progress_chunk(sent_count * part_size, file_size)

        sent_bytes = sent_count * part_size
        while sent_count < part_count:
            if cancel_token is not None and cancel_token.is_cancelled():
                raise UploadCancelled()

            effective_workers = (
                min(num_workers, _background_backoff_workers())
                if priority == "background" and foreground_recently_active()
                else num_workers
            )
            round_count = min(effective_workers, part_count - sent_count)
            round_parts = []
            for i in range(round_count):
                part_index = sent_count + i
                offset = part_index * part_size
                stream.seek(offset)
                part_bytes = stream.read(part_size)
                if part_bytes is None:
                    part_bytes = b""
                if not is_big:
                    md5.update(part_bytes)
                if is_big:
                    request = functions.upload.SaveBigFilePartRequest(
                        file_id, part_index, part_count, part_bytes
                    )
                else:
                    request = functions.upload.SaveFilePartRequest(
                        file_id, part_index, part_bytes
                    )
                round_parts.append((part_index, part_bytes, request))

            results = await _with_telethon_lock(
                asyncio.gather(*[client(req) for _, _, req in round_parts], return_exceptions=True),
                priority,
            )
            restart_fresh_now = False
            for r in results:
                if isinstance(r, BaseException):
                    if _is_missing_part_error(r):

                        logger.warning(
                            "Upload part missing (file_id=%s part_size=%s part_count=%s "
                            "sent_count=%s resumed=%s restarted_already=%s): %s",
                            file_id, part_size, part_count, sent_count,
                            resumed_attempt, restarted_fresh, r,
                        )
                        if not restarted_fresh:
                            restart_fresh_now = True
                            break
                    raise r
            if restart_fresh_now:

                restarted_fresh = True
                resumed_attempt = False
                file_id = int.from_bytes(os.urandom(8), signed=True, byteorder="little")
                sent_count = 0
                sent_bytes = 0
                if md5 is not None:
                    md5 = hashlib.md5()

                if on_part_done:
                    on_part_done(file_id, part_size, 0)
                if on_progress_chunk:
                    on_progress_chunk(0, file_size)
                continue
            for r in results:
                if not r:

                    raise RuntimeError("Failed to upload a file part to Telegram.")

            round_bytes = sum(len(d) for _, d, _ in round_parts)
            sent_bytes += round_bytes
            if on_progress_chunk:
                on_progress_chunk(sent_bytes, file_size)
            sent_count += round_count
            if on_part_done:
                on_part_done(file_id, part_size, sent_count)

        if is_big:
            file_handle = types.InputFileBig(file_id, part_count, filename)
        else:

            file_handle = custom.InputSizedFile(
                file_id, part_count, filename, md5=md5, size=file_size
            )

        kwargs = {"force_document": True, "attributes": [DocumentAttributeFilename(filename)]}
        if thumb_bytes is not None:
            kwargs["thumb"] = thumb_bytes
        if reply_to is not None:
            kwargs["reply_to"] = reply_to
        message = await _with_telethon_lock(client.send_file(chat_id, file=file_handle, **kwargs), priority)
        return message.id
    finally:
        if own_stream:
            stream.close()

def download_thumbnail(chat_id, message_id):

    client = _require_client()

    async def _do():
        message = await client.get_messages(_chat_id_to_peer(chat_id), ids=message_id)
        if message is None:
            raise ValueError(
                "This file's message no longer exists in Telegram - it may have been removed outside the app."
            )
        return await client.download_media(message, thumb=-1, file=bytes)

    return _run_coro_retry_on_lock(_do, timeout=60)

def delete_documents(chat_id, message_ids):
    client = _require_client()

    async def _do():
        await client.delete_messages(_chat_id_to_peer(chat_id), message_ids)

    run_coro(_do(), timeout=60)

def download_range_stream(chat_id, message_id, offset, length):

    client = _require_client()
    aligned_offset = (offset // 4096) * 4096
    skip = offset - aligned_offset

    async def _resolve():
        message = await client.get_messages(_chat_id_to_peer(chat_id), ids=message_id)
        if message is None:
            raise ValueError(
                "This file's message no longer exists in Telegram - it may have been removed outside the app."
            )
        return message

    message = _run_coro_retry_on_lock(_resolve, timeout=60)
    gen = client.iter_download(message, offset=aligned_offset, request_size=524288)

    BATCH = 8

    async def _next_batch():
        pieces = []
        for _ in range(BATCH):
            try:
                pieces.append(await gen.__anext__())
            except StopAsyncIteration:
                break
        return pieces

    emitted = 0
    try:
        while emitted < length:
            batch = run_coro(_next_batch(), timeout=60)
            if not batch:
                return
            for raw_piece in batch:
                if emitted >= length:
                    return

                piece = bytes(raw_piece)
                if skip:
                    if skip >= len(piece):
                        skip -= len(piece)
                        continue
                    piece = piece[skip:]
                    skip = 0
                remaining = length - emitted
                if len(piece) > remaining:
                    piece = piece[:remaining]
                if piece:
                    emitted += len(piece)
                    yield piece
    finally:
        try:
            run_coro(gen.close(), timeout=10)
        except Exception:
            pass

def download_range_parallel(chat_id, message_id, offset, length, num_workers=DOWNLOAD_PARALLEL_WORKERS):

    client = _require_client()
    request_size = 524288
    aligned_offset = (offset // 4096) * 4096
    skip = offset - aligned_offset
    n_pieces = math.ceil((skip + length) / request_size) if length else 0
    num_workers = max(1, min(num_workers, n_pieces or 1))

    async def _resolve():
        message = await client.get_messages(_chat_id_to_peer(chat_id), ids=message_id)
        if message is None:
            raise ValueError(
                "This file's message no longer exists in Telegram - it may have been removed outside the app."
            )
        return message

    message = _run_coro_retry_on_lock(_resolve, timeout=60)
    gens = [
        client.iter_download(
            message,
            offset=aligned_offset + i * request_size,
            stride=num_workers * request_size,
            request_size=request_size,
        )
        for i in range(num_workers)
    ]

    async def _one_piece(worker_gen):
        try:
            return await worker_gen.__anext__()
        except StopAsyncIteration:
            return None

    async def _next_round():

        results = await asyncio.gather(*(_one_piece(g) for g in gens), return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                raise result
        return results

    async def _close_all():

        await asyncio.gather(*(g.close() for g in gens), return_exceptions=True)

    emitted = 0
    try:
        while emitted < length:

            round_pieces = None
            for attempt in range(5):
                try:
                    round_pieces = run_coro(_next_round(), timeout=60)
                    break
                except TimeoutError:
                    if attempt == 4:
                        raise
            if all(p is None for p in round_pieces):
                return
            for raw_piece in round_pieces:
                if raw_piece is None or emitted >= length:
                    continue
                piece = bytes(raw_piece)
                if skip:
                    if skip >= len(piece):
                        skip -= len(piece)
                        continue
                    piece = piece[skip:]
                    skip = 0
                remaining = length - emitted
                if len(piece) > remaining:
                    piece = piece[:remaining]
                if piece:
                    emitted += len(piece)
                    yield piece
    finally:
        try:
            run_coro(_close_all(), timeout=10)
        except Exception:
            pass

META_PREFIX = "[Vault]"

def _format_meta(file_id, filename):
    return f"{META_PREFIX} ID: {file_id}  Name: {filename}"

def send_meta_message(chat_id, reply_to_message_id, file_id, filename):

    client = _require_client()
    async def _do():
        msg = await client.send_message(_chat_id_to_peer(chat_id), _format_meta(file_id, filename), reply_to=reply_to_message_id)
        return msg.id
    try:
        return run_coro(_do(), timeout=30)
    except Exception:
        return None

def update_meta_message(chat_id, meta_message_id, file_id, new_filename, old_filename=None):

    client = _require_client()
    parts = [_format_meta(file_id, new_filename)]
    if old_filename and old_filename != new_filename:
        parts.append(f"← originally: {old_filename}")
    new_text = "\n".join(parts)
    async def _do():
        await client.edit_message(_chat_id_to_peer(chat_id), meta_message_id, new_text)
    try:
        run_coro(_do(), timeout=30)
        return True
    except Exception:
        return False

def delete_meta_message(chat_id, meta_message_id):

    client = _require_client()
    async def _do():
        await client.delete_messages(_chat_id_to_peer(chat_id), [meta_message_id])
    try:
        run_coro(_do(), timeout=30)
        return True
    except Exception:
        return False

_TAGGED_CHUNK_NAME_RE = re.compile(r"^(.*)\.([0-9a-f]{16})\.part(\d+)of(\d+)(\.[^./\\]*)?$")

_LEGACY_CHUNK_NAME_RE = re.compile(r"^(.*)\.part(\d+)of(\d+)(\.[^./\\]*)?$")

def _import_single(chat_id, message, name_override=None):
    name = name_override or message.file.name or f"telegram_{message.id}{message.file.ext or ''}"
    store.create_file({
        "name": name,
        "folder_id": None,
        "size_bytes": message.file.size,
        "mime_type": message.file.mime_type,
        "telegram_chat_id": chat_id,
        "chunks": [{"message_id": message.id, "size_bytes": message.file.size}],
        "source": "backfill",
    })

def _is_same_chat(raw_chat_id, chat_id_int):

    if raw_chat_id is None:
        return False
    try:
        return int(raw_chat_id) == chat_id_int
    except (TypeError, ValueError):
        return False

def backfill_scan(force_full=False):

    client = _require_client()
    chat_id = require_archive_chat()

    try:
        chat_id_int = int(chat_id)
    except (TypeError, ValueError):
        chat_id_int = chat_id
    existing_message_ids = {
        c["message_id"]
        for f in store.load_files()
        if _is_same_chat(f["telegram_chat_id"], chat_id_int)
        for v in f["versions"]
        for c in v["chunks"]
    }

    settings = store.load_settings()
    scanned_chat_id = settings.get("backfill_scanned_chat_id")
    scanned_up_to = settings.get("backfill_scanned_up_to_message_id") or 0
    if force_full or not _is_same_chat(scanned_chat_id, chat_id_int):
        min_id = 0
    else:
        min_id = int(scanned_up_to)

    async def _do():
        skipped = 0

        app_data_message_ids = set()
        try:
            entity = await client.get_input_entity(chat_id)
            app_data_topic_id = await _get_app_data_topic_id(client, entity)
            if app_data_topic_id is not None:
                async for message in client.iter_messages(chat_id, reply_to=app_data_topic_id):
                    app_data_message_ids.add(message.id)
        except Exception:
            pass

        meta_by_reply_to = {}
        candidates = []

        highest_scanned = min_id

        async for message in client.iter_messages(chat_id, min_id=min_id):
            if message.id > highest_scanned:
                highest_scanned = message.id

            if message.message and message.message.startswith(META_PREFIX):
                m = re.match(r"^\[Vault\] ID: (\S+)  Name: ([^\n]+)", message.message)
                if m and message.reply_to_msg_id:
                    meta_by_reply_to[message.reply_to_msg_id] = m.group(2)
                continue

            if not message.file:
                continue
            if message.id in existing_message_ids or message.id in app_data_message_ids:
                skipped += 1
                continue
            candidates.append(message)

        groups = {}
        singles = []
        for message in candidates:
            name = message.file.name or f"telegram_{message.id}{message.file.ext or ''}"
            tagged = _TAGGED_CHUNK_NAME_RE.match(name)
            if tagged:
                base, tag, part_num, total_parts, ext = (
                    tagged.group(1), tagged.group(2), int(tagged.group(3)), int(tagged.group(4)),
                    tagged.group(5) or "",
                )
                groups.setdefault((base, tag, total_parts, ext), []).append((part_num, message))
                continue
            legacy = _LEGACY_CHUNK_NAME_RE.match(name)
            if legacy:
                base, part_num, total_parts, ext = (
                    legacy.group(1), int(legacy.group(2)), int(legacy.group(3)), legacy.group(4) or "",
                )

                groups.setdefault((base, None, total_parts, ext), []).append((part_num, message))
                continue
            singles.append(message)

        imported = 0
        for (base, _tag, total_parts, ext), parts in groups.items():
            part_nums = sorted(p for p, _ in parts)
            if len(parts) == total_parts and part_nums == list(range(1, total_parts + 1)):
                ordered = [msg for _, msg in sorted(parts, key=lambda p: p[0])]
                full_name = base + ext

                meta_name = meta_by_reply_to.get(ordered[0].id)
                if meta_name:
                    full_name = meta_name
                mime_type, _ = mimetypes.guess_type(full_name)
                chunks = [{"message_id": msg.id, "size_bytes": msg.file.size} for msg in ordered]
                store.create_file({
                    "name": full_name,
                    "folder_id": None,
                    "size_bytes": sum(c["size_bytes"] for c in chunks),
                    "mime_type": mime_type,
                    "telegram_chat_id": chat_id,
                    "chunks": chunks,
                    "source": "backfill",
                })
                imported += 1
            else:

                for _, msg in parts:
                    _import_single(chat_id, msg)
                    imported += 1

        for message in singles:
            meta_name = meta_by_reply_to.get(message.id)
            _import_single(chat_id, message, name_override=meta_name)
            imported += 1

        store.save_settings_fields({
            "backfill_scanned_chat_id": chat_id_int,
            "backfill_scanned_up_to_message_id": highest_scanned,
        })

        return imported, skipped

    return run_coro(_do(), timeout=BACKFILL_TIMEOUT)

APP_DATA_TOPIC_TITLE = "App Data (Telegram Vault)"

MEDIA_TOPIC_TITLE = "Media (Images & Video)"

_forum_cache_value = None
_forum_cache_chat = None
_forum_cache_at = 0.0
_forum_cache_lock = threading.Lock()

_FORUM_CACHE_TTL_SECONDS = 300.0

def invalidate_forum_cache():
    global _forum_cache_value, _forum_cache_chat, _forum_cache_at
    with _forum_cache_lock:
        _forum_cache_value = None
        _forum_cache_chat = None
        _forum_cache_at = 0.0

def is_forum_enabled():

    global _forum_cache_value, _forum_cache_chat, _forum_cache_at
    chat_id = require_archive_chat()
    with _forum_cache_lock:
        if (_forum_cache_value is not None
                and _forum_cache_chat == chat_id
                and (time.monotonic() - _forum_cache_at) < _FORUM_CACHE_TTL_SECONDS):
            return _forum_cache_value

    client = _require_client()

    async def _do():
        entity = await client.get_entity(chat_id)
        return bool(getattr(entity, "forum", False))

    enabled = _run_coro_retry_on_lock(_do, timeout=30)
    with _forum_cache_lock:
        _forum_cache_value = enabled
        _forum_cache_chat = chat_id
        _forum_cache_at = time.monotonic()
    return enabled

def check_archive_identity():

    result = {"local_file_count": 0, "local_mismatch_chat_id": None, "has_backup_history": None}
    try:
        chat_id = require_archive_chat()
    except Exception:
        return result

    try:
        files = [f for f in store.load_files() if not f["deleted"]]
        result["local_file_count"] = len(files)
        def _normalize(cid):
            s = str(cid)
            return int(s[4:]) if s.startswith("-100") else int(s)
        chat_id_norm = _normalize(chat_id)
        file_norms = {_normalize(f["telegram_chat_id"]) for f in files}
        mismatched_norm = file_norms - {chat_id_norm}
        if mismatched_norm:
            result["local_mismatch_chat_id"] = f"-100{next(iter(mismatched_norm))}"
    except Exception:
        pass

    try:
        if is_forum_enabled():
            result["has_backup_history"] = bool(list_app_data_snapshots())
        else:
            result["has_backup_history"] = False
    except Exception:
        pass

    return result

def set_forum_mode(enabled):

    client = _require_client()
    chat_id = require_archive_chat()

    async def _do():
        entity = await client.get_input_entity(chat_id)
        await client(ToggleForumRequest(channel=entity, enabled=enabled, tabs=False))

    _run_coro_retry_on_lock(_do, timeout=30)

    invalidate_forum_cache()

async def _get_topic_id_by_title(client, entity, title):

    try:
        existing = await client(GetForumTopicsRequest(
            peer=entity, offset_date=None, offset_id=0, offset_topic=0, limit=100,
        ))
    except ChannelForumMissingError:

        raise ValueError(
            "Topics/Forum mode isn't enabled on your archive group yet - turn it on in Settings first."
        )
    for topic in existing.topics:
        if getattr(topic, "title", None) == title:
            return topic.id
    return None

async def _get_app_data_topic_id(client, entity):
    return await _get_topic_id_by_title(client, entity, APP_DATA_TOPIC_TITLE)

def _find_or_create_topic(client, chat_id, title):

    async def _do():
        entity = await client.get_input_entity(chat_id)
        topic_id = await _get_topic_id_by_title(client, entity, title)
        if topic_id is not None:
            return topic_id
        result = await client(CreateForumTopicRequest(
            peer=entity, title=title,
            random_id=telethon_helpers.generate_random_long(),
        ))

        for update in getattr(result, "updates", []) or []:
            message = getattr(update, "message", None)
            if message is not None:
                return message.id
        raise ValueError("Telegram didn't return the new topic's id - can't continue.")

    return _run_coro_retry_on_lock(_do, timeout=30)

def _find_or_create_app_data_topic(client, chat_id):
    return _find_or_create_topic(client, chat_id, APP_DATA_TOPIC_TITLE)

def find_or_create_media_topic():

    client = _require_client()
    chat_id = require_archive_chat()
    return _find_or_create_topic(client, chat_id, MEDIA_TOPIC_TITLE)

def forward_message_to_media_topic(message_id):

    client = _require_client()
    chat_id = require_archive_chat()
    topic_id = _find_or_create_topic(client, chat_id, MEDIA_TOPIC_TITLE)

    async def _do():
        entity = await client.get_input_entity(chat_id)
        result = await client(ForwardMessagesRequest(
            from_peer=entity, id=[message_id], to_peer=entity,
            top_msg_id=topic_id, random_id=[telethon_helpers.generate_random_long()],
        ))
        for update in getattr(result, "updates", []) or []:
            message = getattr(update, "message", None)
            if message is not None:
                return message.id
        raise ValueError("Telegram didn't return the forwarded message's id - can't continue.")

    return _run_coro_retry_on_lock(_do, timeout=60)

def media_topic_message_ids():

    client = _require_client()
    chat_id = require_archive_chat()

    async def _do():
        entity = await client.get_input_entity(chat_id)
        topic_id = await _get_topic_id_by_title(client, entity, MEDIA_TOPIC_TITLE)
        if topic_id is None:
            return set()
        ids = set()
        async for message in client.iter_messages(chat_id, reply_to=topic_id):
            ids.add(message.id)
        return ids

    return _run_coro_retry_on_lock(_do, timeout=60)

def upload_app_data_snapshot(snapshot_bytes, filename, on_progress=None):

    client = _require_client()
    chat_id = require_archive_chat()
    topic_id = _find_or_create_app_data_topic(client, chat_id)

    async def _do():
        message = await client.send_file(
            chat_id, file=io.BytesIO(snapshot_bytes), attributes=[DocumentAttributeFilename(filename)],
            force_document=True, reply_to=topic_id, progress_callback=on_progress,
        )
        return message.id

    return _run_coro_retry_on_lock(_do, timeout=120)

def list_app_data_snapshots():

    client = _require_client()
    chat_id = require_archive_chat()

    async def _do():
        entity = await client.get_input_entity(chat_id)
        topic_id = await _get_app_data_topic_id(client, entity)
        if topic_id is None:
            return []
        snapshots = []
        async for message in client.iter_messages(chat_id, reply_to=topic_id):
            if not message.file:
                continue
            snapshots.append({
                "message_id": message.id,
                "date": message.date.isoformat(),
                "size_bytes": message.file.size,
                "filename": message.file.name,
            })
        return snapshots

    return _run_coro_retry_on_lock(_do, timeout=30)

def delete_app_data_snapshots(message_ids):

    if message_ids:
        delete_documents(require_archive_chat(), message_ids)

def download_app_data_snapshot(message_id, on_progress=None):

    client = _require_client()
    chat_id = require_archive_chat()

    async def _do():
        message = await client.get_messages(_chat_id_to_peer(chat_id), ids=message_id)
        if message is None:
            raise ValueError("This snapshot no longer exists in Telegram - it may have been removed outside the app.")
        return await client.download_media(message, file=bytes, progress_callback=on_progress)

    return _run_coro_retry_on_lock(_do, timeout=60)
