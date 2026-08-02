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

def test_refresh_premium_status_updates_settings(isolated_store):
    isolated_store.save_settings_fields({"is_premium": False})

    with patch("telegram_client._require_client", return_value=MagicMock()), \
         patch("telegram_client.run_coro", return_value=True):
        result = telegram_client.refresh_premium_status()

    assert result is True
    assert isolated_store.load_settings()["is_premium"] is True

def test_refresh_premium_status_does_not_touch_custom_chunk_size(isolated_store):

    isolated_store.save_settings_fields({"is_premium": False, "max_chunk_size_bytes": 500_000_000})

    with patch("telegram_client._require_client", return_value=MagicMock()), \
         patch("telegram_client.run_coro", return_value=True):
        telegram_client.refresh_premium_status()

    assert isolated_store.load_settings()["max_chunk_size_bytes"] == 500_000_000

def test_refresh_premium_status_updates_default_chunk_size(isolated_store):

    isolated_store.save_settings_fields({"is_premium": False, "max_chunk_size_bytes": 1_900_000_000})

    with patch("telegram_client._require_client", return_value=MagicMock()), \
         patch("telegram_client.run_coro", return_value=True):
        telegram_client.refresh_premium_status()

    assert isolated_store.load_settings()["max_chunk_size_bytes"] == 3_900_000_000

def test_refresh_premium_status_downgrades_chunk_size(isolated_store):

    isolated_store.save_settings_fields({"is_premium": True, "max_chunk_size_bytes": 3_900_000_000})

    with patch("telegram_client._require_client", return_value=MagicMock()), \
         patch("telegram_client.run_coro", return_value=False):
        telegram_client.refresh_premium_status()

    assert isolated_store.load_settings()["is_premium"] is False
    assert isolated_store.load_settings()["max_chunk_size_bytes"] == 1_900_000_000

def test_refresh_premium_status_route_returns_updated_value(client, isolated_store):
    isolated_store.save_settings_fields({"is_premium": False})

    with patch("telegram_client.refresh_premium_status", return_value=True):
        resp = client.post("/api/telegram/refresh-premium-status")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["is_premium"] is True
    assert "max_chunk_size_bytes" in data

def test_refresh_premium_status_route_reports_error(client, isolated_store):
    with patch("telegram_client.refresh_premium_status", side_effect=ValueError("Telegram isn't connected yet - set it up in Settings first.")):
        resp = client.post("/api/telegram/refresh-premium-status")

    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False
    assert "Telegram isn't connected yet" in data["error"]
