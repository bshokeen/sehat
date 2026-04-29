"""Tests for Sehat data models."""

import pytest
from datetime import datetime

from sehat.models import (
    ReminderType, ReminderConfig, SehatConfig, LogEntry,
    ExerciseInfo, DailyStats, SehatStatus,
)


class TestReminderType:
    def test_all_types(self):
        expected = {"eyes", "posture", "neck_stretch", "stand", "water", "full_break", "workout"}
        assert {t.value for t in ReminderType} == expected

    def test_string_enum(self):
        assert ReminderType.EYES == "eyes"
        assert isinstance(ReminderType.EYES, str)


class TestReminderConfig:
    def test_minimal(self):
        rc = ReminderConfig(interval_min=20)
        assert rc.enabled is True
        assert rc.jitter_min == 0
        assert rc.align_to_clock is None

    def test_full(self):
        rc = ReminderConfig(
            enabled=True, interval_min=45, duration_sec=90,
            jitter_min=5, align_to_clock=55,
            active_hours=[{"start": "06:00", "end": "09:00"}]
        )
        assert rc.interval_min == 45
        assert rc.active_hours[0]["start"] == "06:00"

    def test_disabled(self):
        rc = ReminderConfig(enabled=False, interval_min=30)
        assert rc.enabled is False


class TestSehatConfig:
    def test_from_default_config(self):
        import json
        from pathlib import Path
        default = Path(__file__).parent.parent / "sehat" / "default_config.json"
        data = json.loads(default.read_text(encoding="utf-8"))
        cfg = SehatConfig(**data)
        assert len(cfg.reminders) == 7
        assert cfg.level == 1
        assert cfg.dnd is False

    def test_active_days_default(self):
        cfg = SehatConfig(reminders={
            "eyes": ReminderConfig(interval_min=20)
        })
        assert "Mon" in cfg.active_days

    def test_invalid_reminder_missing_interval(self):
        with pytest.raises(Exception):
            ReminderConfig()


class TestLogEntry:
    def test_basic_event(self):
        entry = LogEntry(ts=datetime.now(), event="session_start")
        assert entry.type is None

    def test_reminder_event(self):
        entry = LogEntry(ts=datetime.now(), event="reminder", type="eyes")
        assert entry.type == "eyes"

    def test_done_event(self):
        entry = LogEntry(ts=datetime.now(), event="done", type="posture", duration_sec=15)
        assert entry.duration_sec == 15


class TestExerciseInfo:
    def test_full(self):
        ex = ExerciseInfo(
            id="chin_tucks", name="Chin Tucks", type="neck_stretch",
            level=1, duration_sec=60, steps=["Step 1", "Step 2"]
        )
        assert ex.id == "chin_tucks"
        assert len(ex.steps) == 2
        assert ex.warning is None


class TestDailyStats:
    def test_full(self):
        stats = DailyStats(
            date="2026-04-28", total_reminders=10, done=7,
            skipped=2, snoozed=1, compliance_pct=70.0,
            active_min=480, dnd_min=30
        )
        assert stats.compliance_pct == 70.0


class TestSehatStatus:
    def test_inactive(self):
        status = SehatStatus(session_active=False)
        assert status.active_min == 0
        assert status.dnd is False
        assert status.today_score == 0.0
