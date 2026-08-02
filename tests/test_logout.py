from unittest.mock import MagicMock, patch

import pytest

import app
import telegram_client
from tests.conftest import isolated_store

@pytest.fixture
def client(isolated_store):
    app.app.config["TESTING"] = True
    with app.app.test_client() as client:
        yield client

def test_logout_clears_account_specific_settings_but_keeps_app_credentials(isolated_store):
    isolated_store.save_settings_fields({
        "api_id": 12345, "api_hash": "abc123",
        "phone_number": "+1234567890", "archive_chat_id": "-100999",
        "archive_chat_title": "Vault Archive", "is_premium": True,
        "app_data_backup_last_known_message_id": 42,
        "sync_pairs": [{"id": "p1", "local_path": "/fake"}],
    })

    fake_client = MagicMock()
    with patch("telegram_client._client", fake_client), \
         patch("telegram_client.run_coro", return_value=None):
        telegram_client.logout()

    settings = isolated_store.load_settings()

    assert settings["archive_chat_id"] is None
    assert settings["archive_chat_title"] is None
    assert settings["is_premium"] is False
    assert settings["app_data_backup_last_known_message_id"] is None

    assert settings["api_id"] == 12345
    assert settings["api_hash"] == "abc123"
    assert settings["phone_number"] == "+1234567890"

    assert settings["sync_pairs"] == [{"id": "p1", "local_path": "/fake"}]

def test_logout_resets_in_memory_client_to_none(isolated_store):

    fake_client = MagicMock()
    with patch("telegram_client._client", fake_client), \
         patch("telegram_client.run_coro", return_value=None):
        telegram_client.logout()

    assert telegram_client._client is None

def test_logout_deletes_encrypted_session_file(isolated_store, tmp_path):
    session_path = tmp_path / "telegram_vault.session.enc"
    session_path.write_bytes(b"fake encrypted session")

    with patch("credential_store.ENCRYPTED_SESSION_PATH", str(session_path)), \
         patch("telegram_client._client", None):
        telegram_client.logout()

    assert not session_path.exists()

def test_logout_is_best_effort_if_telegram_log_out_call_fails(isolated_store):

    fake_client = MagicMock()

    def _raise(*args, **kwargs):
        raise ConnectionError("network down")

    isolated_store.save_settings_fields({"phone_number": "+1234567890", "archive_chat_id": "-100999"})
    with patch("telegram_client._client", fake_client), \
         patch("telegram_client.run_coro", side_effect=_raise):
        telegram_client.logout()

    assert isolated_store.load_settings()["archive_chat_id"] is None

    assert isolated_store.load_settings()["phone_number"] == "+1234567890"
    assert telegram_client._client is None

def test_logout_route_returns_ok(client, isolated_store):
    with patch("telegram_client.logout") as mock_logout:
        resp = client.post("/api/telegram/logout")

    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}
    mock_logout.assert_called_once()

def test_logout_route_reports_error(client, isolated_store):
    with patch("telegram_client.logout", side_effect=ValueError("boom")):
        resp = client.post("/api/telegram/logout")

    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False
    assert "boom" in data["error"]
