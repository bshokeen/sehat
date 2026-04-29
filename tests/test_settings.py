"""Tests for settings read-modify-write logic."""

import json
from pathlib import Path

import pytest

from sehat.models import SehatConfig


@pytest.fixture
def config_with_advanced_fields(tmp_path):
    """Config with jitter, align_to_clock, active_hours that must survive save."""
    cfg = {
        "conditions": ["neck_strain", "eye_strain"],
        "reminders": {
            "eyes": {"enabled": True, "interval_min": 20, "duration_sec": 20, "jitter_min": 5},
            "posture": {"enabled": True, "interval_min": 30, "duration_sec": 15, "jitter_min": 5},
            "water": {"enabled": True, "interval_min": 60, "duration_sec": 10, "align_to_clock": 55},
            "neck_stretch": {"enabled": True, "interval_min": 45, "duration_sec": 90},
            "stand": {"enabled": True, "interval_min": 60, "duration_sec": 180},
            "full_break": {"enabled": True, "interval_min": 120, "duration_sec": 600},
            "workout": {
                "enabled": True, "interval_min": 240, "duration_sec": 1800,
                "active_hours": [{"start": "06:00", "end": "09:00"}, {"start": "17:00", "end": "21:00"}]
            },
        },
        "quiet_ranges": [{"start": "22:00", "end": "07:00"}],
        "active_days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "level": 1,
        "dnd": False,
        "auto_close_sec": 20,
        "popup_monitor": "primary",
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return path, cfg


def simulate_settings_save(config_path: Path, changes: dict) -> dict:
    """Simulate the read-modify-write that SettingsWindow._save() does."""
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    reminders = raw.get("reminders", {})

    for rtype, vals in changes.get("reminders", {}).items():
        if rtype not in reminders:
            reminders[rtype] = {}
        for k, v in vals.items():
            reminders[rtype][k] = v
    raw["reminders"] = reminders

    for key in ("active_days", "quiet_ranges", "auto_close_sec", "popup_monitor", "level"):
        if key in changes:
            raw[key] = changes[key]

    # Validate
    SehatConfig(**raw)

    # Atomic write
    tmp = config_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    tmp.replace(config_path)
    return raw


class TestSettingsRoundTrip:
    def test_preserves_jitter_min(self, config_with_advanced_fields):
        path, original = config_with_advanced_fields
        simulate_settings_save(path, {
            "reminders": {"eyes": {"interval_min": 25}}
        })
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved["reminders"]["eyes"]["jitter_min"] == 5
        assert saved["reminders"]["eyes"]["interval_min"] == 25

    def test_preserves_align_to_clock(self, config_with_advanced_fields):
        path, original = config_with_advanced_fields
        simulate_settings_save(path, {
            "reminders": {"water": {"enabled": False}}
        })
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved["reminders"]["water"]["align_to_clock"] == 55
        assert saved["reminders"]["water"]["enabled"] is False

    def test_preserves_active_hours(self, config_with_advanced_fields):
        path, original = config_with_advanced_fields
        simulate_settings_save(path, {
            "reminders": {"workout": {"interval_min": 180}}
        })
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved["reminders"]["workout"]["active_hours"] == [
            {"start": "06:00", "end": "09:00"},
            {"start": "17:00", "end": "21:00"},
        ]

    def test_preserves_conditions(self, config_with_advanced_fields):
        path, original = config_with_advanced_fields
        simulate_settings_save(path, {"level": 2})
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved["conditions"] == ["neck_strain", "eye_strain"]

    def test_changes_active_days(self, config_with_advanced_fields):
        path, _ = config_with_advanced_fields
        simulate_settings_save(path, {
            "active_days": ["Mon", "Wed", "Fri"]
        })
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved["active_days"] == ["Mon", "Wed", "Fri"]

    def test_changes_quiet_hours(self, config_with_advanced_fields):
        path, _ = config_with_advanced_fields
        simulate_settings_save(path, {
            "quiet_ranges": [{"start": "23:00", "end": "06:00"}]
        })
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved["quiet_ranges"][0]["start"] == "23:00"

    def test_full_config_still_valid(self, config_with_advanced_fields):
        path, _ = config_with_advanced_fields
        saved = simulate_settings_save(path, {
            "reminders": {
                "eyes": {"enabled": False, "interval_min": 30, "duration_sec": 25},
                "workout": {"interval_min": 300},
            },
            "active_days": ["Mon", "Tue"],
            "auto_close_sec": 30,
            "popup_monitor": "active",
            "level": 3,
        })
        cfg = SehatConfig(**saved)
        assert cfg.reminders["eyes"].enabled is False
        assert cfg.reminders["workout"].interval_min == 300
        assert cfg.level == 3
