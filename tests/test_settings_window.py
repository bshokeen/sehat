"""Tests for the Sehat Settings dialog (read-modify-write logic + new fields).

The dialog itself needs a Tk display, so we cover behavior in two layers:

  1. SehatConfig accepts the new popup_stay_sec and popup_monitor fields.
  2. End-to-end save round-trips through SettingsWindow when a Tk display
     is available (skipped on headless systems).
  3. Pure-Python helpers (_split_hhmm, _coerce_int_str) work correctly.
"""

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from sehat.models import ReminderConfig, SehatConfig
from sehat.settings_window import (
    _coerce_int_str,
    _split_hhmm,
)


# ── Schema-level tests (no Tk needed) ──────────────────────────────────


class TestSchemaAdditions:
    """Both new fields are optional and default to None / 'primary'."""

    def test_popup_stay_sec_defaults_none(self):
        rc = ReminderConfig(interval_min=20)
        assert rc.popup_stay_sec is None

    def test_popup_stay_sec_accepts_int(self):
        rc = ReminderConfig(interval_min=20, popup_stay_sec=45)
        assert rc.popup_stay_sec == 45

    def test_popup_monitor_default_primary(self):
        cfg = SehatConfig(reminders={"eyes": ReminderConfig(interval_min=20)})
        assert cfg.popup_monitor == "primary"

    def test_popup_monitor_accepts_active(self):
        cfg = SehatConfig(
            reminders={"eyes": ReminderConfig(interval_min=20)},
            popup_monitor="active",
        )
        assert cfg.popup_monitor == "active"

    def test_existing_configs_validate(self):
        """Configs without the new fields must still validate."""
        cfg_dict = {
            "reminders": {
                "eyes": {"enabled": True, "interval_min": 20, "duration_sec": 20},
            },
            "quiet_hours": {"start": "22:00", "end": "07:00"},
            "level": 1,
            "auto_close_sec": 20,
        }
        cfg = SehatConfig(**cfg_dict)
        assert cfg.reminders["eyes"].popup_stay_sec is None
        assert cfg.popup_monitor == "primary"


# ── Pure helpers ────────────────────────────────────────────────────────


class TestHelpers:
    @pytest.mark.parametrize("hhmm,expected", [
        ("22:00", (22, 0)),
        ("07:30", (7, 30)),
        ("00:00", (0, 0)),
        ("23:59", (23, 59)),
    ])
    def test_split_hhmm_valid(self, hhmm, expected):
        assert _split_hhmm(hhmm) == expected

    @pytest.mark.parametrize("bad", ["bad", "", None, "12"])
    def test_split_hhmm_unparseable_returns_zero(self, bad):
        """Strings that can't be split into HH:MM at all → (0, 0)."""
        assert _split_hhmm(bad) == (0, 0)

    def test_split_hhmm_clamps_hour(self):
        """Hour > 23 gets clamped to 23 (function is forgiving, not strict)."""
        h, m = _split_hhmm("25:00")
        assert h == 23 and m == 0

    def test_split_hhmm_clamps_minute(self):
        """Minute > 59 gets clamped to 59."""
        h, m = _split_hhmm("12:60")
        assert h == 12 and m == 59

    def test_split_hhmm_clamps_oversize(self):
        # Hour > 23 gets clamped to 23
        h, m = _split_hhmm("99:99")
        assert 0 <= h <= 23
        assert 0 <= m <= 59

    def test_coerce_int_str_none(self):
        assert _coerce_int_str(None) == ""

    def test_coerce_int_str_none_with_default(self):
        assert _coerce_int_str(None, default="30") == "30"

    def test_coerce_int_str_int_value(self):
        assert _coerce_int_str(42) == "42"

    def test_coerce_int_str_zero(self):
        assert _coerce_int_str(0) == "0"


# ── Read-modify-write round-trip (with Tk) ──────────────────────────────

# Most of the dialog logic requires a Tk root. Skip cleanly on headless.
tk = pytest.importorskip("tkinter")


@pytest.fixture
def tk_root():
    """Provide a hidden Tk root or skip if no display."""
    try:
        root = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"No Tk display available: {e}")
    root.withdraw()
    yield root
    try:
        root.destroy()
    except Exception:
        pass


@pytest.fixture
def cfg_path(tmp_path):
    """Config that mirrors the current default + advanced fields that must survive."""
    cfg = {
        "conditions": ["neck_strain", "eye_strain"],
        "reminders": {
            "eyes": {"enabled": True, "interval_min": 20, "duration_sec": 20, "jitter_min": 5},
            "posture": {"enabled": True, "interval_min": 30, "duration_sec": 15, "jitter_min": 5},
            "water": {"enabled": True, "interval_min": 60, "duration_sec": None, "align_to_clock": 55},
            "neck_stretch": {"enabled": True, "interval_min": 30, "duration_sec": 90},
            "stand": {"enabled": True, "interval_min": 60, "duration_sec": 180},
            "full_break": {"enabled": True, "interval_min": 120, "duration_sec": 600},
            # NOTE: workout intentionally absent — verifies "missing reminder" handling
        },
        "quiet_hours": {"start": "22:00", "end": "07:00"},
        "active_days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "level": 1,
        "dnd": False,
        "auto_close_sec": 20,
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return path


class TestSettingsRoundTrip:
    def test_dialog_constructs_with_real_config(self, tk_root, cfg_path):
        from sehat.settings_window import SettingsWindow
        sw = SettingsWindow(tk_root, cfg_path)
        sw.top.update_idletasks()
        try:
            assert len(sw._reminder_vars) == 7  # all 7 types shown
            assert sw._qs_min == 22 * 60
            assert sw._qe_min == 7 * 60
        finally:
            sw.top.destroy()

    def test_save_preserves_jitter_min(self, tk_root, cfg_path):
        from sehat.settings_window import SettingsWindow
        sw = SettingsWindow(tk_root, cfg_path)
        sw._reminder_vars["eyes"]["interval_min"].set("25")
        sw._save()
        saved = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert saved["reminders"]["eyes"]["jitter_min"] == 5
        assert saved["reminders"]["eyes"]["interval_min"] == 25

    def test_save_preserves_align_to_clock(self, tk_root, cfg_path):
        from sehat.settings_window import SettingsWindow
        sw = SettingsWindow(tk_root, cfg_path)
        sw._reminder_vars["water"]["enabled"].set(False)
        sw._save()
        saved = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert saved["reminders"]["water"]["align_to_clock"] == 55
        assert saved["reminders"]["water"]["enabled"] is False

    def test_save_preserves_null_duration_sec(self, tk_root, cfg_path):
        """Water has duration_sec=null. Must survive save unchanged when activity field is blank."""
        from sehat.settings_window import SettingsWindow
        sw = SettingsWindow(tk_root, cfg_path)
        # water row's activity field starts empty (since duration_sec was null)
        assert sw._reminder_vars["water"]["duration_sec"].get() == ""
        sw._save()
        saved = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert saved["reminders"]["water"]["duration_sec"] is None

    def test_save_writes_per_reminder_popup_stay(self, tk_root, cfg_path):
        from sehat.settings_window import SettingsWindow
        sw = SettingsWindow(tk_root, cfg_path)
        sw._reminder_vars["workout"]["popup_stay_sec"].set("60")
        sw._reminder_vars["workout"]["enabled"].set(True)  # force-enable so it gets saved
        sw._save()
        saved = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert saved["reminders"]["workout"]["popup_stay_sec"] == 60

    def test_save_writes_quiet_hours_in_both_keys(self, tk_root, cfg_path):
        """Modern quiet_ranges + legacy quiet_hours mirror for backward compat."""
        from sehat.settings_window import SettingsWindow
        sw = SettingsWindow(tk_root, cfg_path)
        sw._qs_min = 23 * 60 + 30
        sw._qe_min = 6 * 60 + 0
        sw._save()
        saved = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert saved["quiet_ranges"][0] == {"start": "23:30", "end": "06:00"}
        assert saved["quiet_hours"] == {"start": "23:30", "end": "06:00"}

    def test_save_does_not_silently_add_missing_disabled_reminder(self, tk_root, cfg_path):
        """Workout was missing from cfg. If user leaves it disabled, don't add it."""
        from sehat.settings_window import SettingsWindow
        sw = SettingsWindow(tk_root, cfg_path)
        sw._reminder_vars["workout"]["enabled"].set(False)
        sw._save()
        saved = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert "workout" not in saved["reminders"]

    def test_save_adds_missing_reminder_when_enabled(self, tk_root, cfg_path):
        """If user enables a reminder that wasn't in config, add it with sensible defaults."""
        from sehat.settings_window import SettingsWindow
        sw = SettingsWindow(tk_root, cfg_path)
        sw._reminder_vars["workout"]["enabled"].set(True)
        sw._save()
        saved = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert "workout" in saved["reminders"]
        assert saved["reminders"]["workout"]["enabled"] is True
        assert saved["reminders"]["workout"]["interval_min"] >= 1

    def test_save_preserves_level_from_config(self, tk_root, cfg_path):
        """Level isn't exposed in UI but must be preserved through save."""
        # Set a non-default level first
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        cfg["level"] = 3
        cfg_path.write_text(json.dumps(cfg))

        from sehat.settings_window import SettingsWindow
        sw = SettingsWindow(tk_root, cfg_path)
        sw._reminder_vars["eyes"]["interval_min"].set("25")
        sw._save()
        saved = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert saved["level"] == 3

    def test_legacy_quiet_hours_only_loads_correctly(self, tk_root, tmp_path):
        """Legacy config with only quiet_hours (no quiet_ranges) should load."""
        cfg = {
            "reminders": {"eyes": {"enabled": True, "interval_min": 20}},
            "quiet_hours": {"start": "21:00", "end": "06:00"},  # legacy only
        }
        path = tmp_path / "legacy.json"
        path.write_text(json.dumps(cfg))

        from sehat.settings_window import SettingsWindow
        sw = SettingsWindow(tk_root, path)
        try:
            assert sw._qs_min == 21 * 60
            assert sw._qe_min == 6 * 60
        finally:
            sw.top.destroy()


# ── Popup-stay precedence (mirrors the inline logic in tray_app._show_popup) ─


def _resolve_popup_stay(cfg: dict, reminder_type: str) -> int:
    """Spec for the popup-stay resolver in tray_app._show_popup.

    Precedence (top wins):
      1. per-reminder popup_stay_sec (if int > 0)
      2. global auto_close_sec       (if int > 0)
      3. 15-second safe default
    """
    auto_close = 15
    g = cfg.get("auto_close_sec", 0)
    if isinstance(g, int) and g > 0:
        auto_close = g
    rc = cfg.get("reminders", {}).get(reminder_type, {})
    ps = rc.get("popup_stay_sec")
    if isinstance(ps, int) and ps > 0:
        auto_close = ps
    return auto_close


class TestPopupStayPrecedence:
    """Documents the resolution order for popup-visible time per reminder."""

    def test_default_when_nothing_set(self):
        cfg = {"reminders": {"eyes": {}}}
        assert _resolve_popup_stay(cfg, "eyes") == 15

    def test_global_auto_close_wins_over_default(self):
        cfg = {"auto_close_sec": 30, "reminders": {"eyes": {}}}
        assert _resolve_popup_stay(cfg, "eyes") == 30

    def test_per_reminder_wins_over_global(self):
        cfg = {"auto_close_sec": 20, "reminders": {"workout": {"popup_stay_sec": 60}}}
        assert _resolve_popup_stay(cfg, "workout") == 60

    def test_blank_per_reminder_falls_back_to_global(self):
        cfg = {"auto_close_sec": 20, "reminders": {"water": {"popup_stay_sec": None}}}
        assert _resolve_popup_stay(cfg, "water") == 20

    def test_zero_per_reminder_treated_as_unset(self):
        """popup_stay_sec=0 must not override (validation forbids it but be defensive)."""
        cfg = {"auto_close_sec": 25, "reminders": {"eyes": {"popup_stay_sec": 0}}}
        assert _resolve_popup_stay(cfg, "eyes") == 25

    def test_unknown_reminder_uses_global(self):
        cfg = {"auto_close_sec": 22, "reminders": {}}
        assert _resolve_popup_stay(cfg, "missing") == 22
