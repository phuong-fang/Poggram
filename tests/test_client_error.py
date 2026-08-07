import sqlite3

import pytest
from telethon.errors import PhoneCodeInvalidError

import shared

class TestMessagesUsersNeedAreKept:

    def test_app_raised_valueerror_is_passed_through(self):
        msg = "That code doesn't match what Telegram sent - check it and try again."
        assert shared.client_error(ValueError(msg)) == msg

    def test_telegram_rpc_error_is_passed_through(self):

        assert "invalid" in shared.client_error(PhoneCodeInvalidError(request=None)).lower()

    def test_connection_error_is_passed_through(self):

        assert shared.client_error(ConnectionError("Not connected")) == "Not connected"

class TestInternalDetailIsHidden:
    def test_oserror_does_not_leak_a_local_path(self):
        exc = OSError(2, "No such file or directory", r"C:\Users\someone\secrets\id_rsa")
        result = shared.client_error(exc)
        assert "id_rsa" not in result and "someone" not in result
        assert result == shared._GENERIC_ERROR

    def test_sqlite_error_does_not_leak_schema(self):
        result = shared.client_error(sqlite3.OperationalError("no such column: files.telegram_chat_id"))
        assert "telegram_chat_id" not in result
        assert result == shared._GENERIC_ERROR

    def test_unexpected_type_is_generic(self):
        assert shared.client_error(KeyError("internal_state")) == shared._GENERIC_ERROR

    def test_caller_can_override_the_fallback(self):
        assert shared.client_error(KeyError("x"), fallback="Backup failed.") == "Backup failed."

def test_hidden_errors_are_still_logged(caplog):

    with caplog.at_level("ERROR"):
        shared.client_error(sqlite3.OperationalError("no such column: files.secret"))
    assert "OperationalError" in caplog.text

@pytest.mark.parametrize("exc", [ValueError(""), ConnectionError("")])
def test_empty_message_falls_back_to_the_type_name(exc):

    assert shared.client_error(exc) == type(exc).__name__
