import asyncio
from unittest.mock import MagicMock, patch

import telegram_client

def _fake_do_parallel_upload_factory(calls):
    def _fake(*args, **kwargs):
        calls.append(kwargs)

        async def _coro():
            return "msg"

        return _coro()

    return _fake

def _run_coro_cancellable_stub(coro_factory, *args, **kwargs):

    return asyncio.run(coro_factory())

def test_chunked_upload_resume_part_state_only_applies_to_in_progress_chunk(tmp_path):
    file_path = tmp_path / "big.bin"
    max_chunk_size = 100
    file_path.write_bytes(b"x" * (max_chunk_size * 3))

    calls = []
    resume_part_state = {"file_id": 999, "part_size": 32, "parts_sent": 2}

    resume_chunks = [{"message_id": 111, "size_bytes": max_chunk_size}]

    with patch("telegram_client._require_client", return_value=MagicMock()), \
         patch("telegram_client.require_archive_chat", return_value="-100999"), \
         patch("telegram_client._do_parallel_upload", side_effect=_fake_do_parallel_upload_factory(calls)), \
         patch("telegram_client.run_coro_cancellable", side_effect=_run_coro_cancellable_stub):
        chat_id, chunks = telegram_client.upload_file_parallel(
            str(file_path), "big.bin", max_chunk_size, num_workers=3,
            resume_chunks=resume_chunks, resume_part_state=resume_part_state,
            on_part_done=lambda *a: None,
        )

    assert chat_id == "-100999"

    assert len(chunks) == 3
    assert chunks[0]["message_id"] == 111

    assert len(calls) == 2

    assert calls[0]["resume_part_state"] == resume_part_state

    assert calls[1]["resume_part_state"] is None

    assert calls[0]["on_part_done"] is not None
    assert calls[1]["on_part_done"] is not None

def test_chunked_upload_no_resume_state_when_starting_fresh(tmp_path):
    file_path = tmp_path / "big.bin"
    max_chunk_size = 100
    file_path.write_bytes(b"x" * (max_chunk_size * 2))

    calls = []

    with patch("telegram_client._require_client", return_value=MagicMock()), \
         patch("telegram_client.require_archive_chat", return_value="-100999"), \
         patch("telegram_client._do_parallel_upload", side_effect=_fake_do_parallel_upload_factory(calls)), \
         patch("telegram_client.run_coro_cancellable", side_effect=_run_coro_cancellable_stub):
        telegram_client.upload_file_parallel(
            str(file_path), "big.bin", max_chunk_size, num_workers=3,
        )

    assert len(calls) == 2
    assert calls[0]["resume_part_state"] is None
    assert calls[1]["resume_part_state"] is None
