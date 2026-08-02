from unittest.mock import patch

import pytest

import shared
from tests.conftest import isolated_store

@pytest.fixture(autouse=True)
def _reset_dirty_cache():

    shared._app_data_dirty = None
    yield
    shared._app_data_dirty = None

def test_marking_a_change_persists_the_flag(isolated_store):
    assert isolated_store.load_settings()["app_data_backup_pending_changes"] is False

    shared.mark_app_data_changed()

    assert isolated_store.load_settings()["app_data_backup_pending_changes"] is True
    assert shared._app_data_is_dirty() is True

def test_repeat_marks_do_not_rewrite_settings(isolated_store):

    shared.mark_app_data_changed()
    with patch.object(isolated_store, "save_settings_fields") as save:
        for _ in range(20):
            shared.mark_app_data_changed()
    save.assert_not_called()

def test_dirty_state_is_read_back_from_settings(isolated_store):

    isolated_store.save_settings_fields({"app_data_backup_pending_changes": True})
    shared._app_data_dirty = None

    assert shared._app_data_is_dirty() is True

def test_on_close_skips_entirely_when_nothing_changed(isolated_store):
    with patch.object(shared, "_run_app_data_snapshot") as run:
        shared.snapshot_now_blocking()
    run.assert_not_called()

def test_on_close_snapshots_when_something_changed(isolated_store):
    shared.mark_app_data_changed()
    with patch.object(shared, "_run_app_data_snapshot") as run:
        shared.snapshot_now_blocking()
    run.assert_called_once()

def test_a_successful_snapshot_clears_the_flag(isolated_store):
    shared.mark_app_data_changed()

    with patch.object(shared, "_do_build_and_upload_app_data_snapshot"):
        shared._build_and_upload_app_data_snapshot()

    assert shared._app_data_is_dirty() is False
    assert isolated_store.load_settings()["app_data_backup_pending_changes"] is False

def test_a_failed_snapshot_leaves_the_flag_set(isolated_store):

    shared.mark_app_data_changed()

    with patch.object(shared, "_do_build_and_upload_app_data_snapshot", side_effect=RuntimeError("upload died")):
        with pytest.raises(RuntimeError):
            shared._build_and_upload_app_data_snapshot()

    assert shared._app_data_is_dirty() is True
    assert isolated_store.load_settings()["app_data_backup_pending_changes"] is True

def test_a_change_during_the_build_is_not_lost(isolated_store):

    shared.mark_app_data_changed()

    def _build_then_something_changes(**kwargs):
        shared.mark_app_data_changed()

    with patch.object(shared, "_do_build_and_upload_app_data_snapshot", side_effect=_build_then_something_changes):
        shared._build_and_upload_app_data_snapshot()

    assert shared._app_data_is_dirty() is True

def test_disabled_backup_does_not_clear_pending_changes(isolated_store):

    shared.mark_app_data_changed()
    isolated_store.save_settings_fields({"app_data_backup_enabled": False})

    shared._run_app_data_snapshot()

    assert shared._app_data_is_dirty() is True

def test_the_debounce_timer_is_really_gone(isolated_store):

    assert not hasattr(shared, "schedule_app_data_snapshot")
    assert not hasattr(shared, "_app_data_snapshot_timer")
    assert not hasattr(shared, "APP_DATA_SNAPSHOT_DEBOUNCE_SECONDS")
