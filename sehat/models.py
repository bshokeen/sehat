"""Data models for Sehat Health Monitor."""

from pydantic import BaseModel
from typing import Optional
from enum import Enum
from datetime import datetime


class ReminderType(str, Enum):
    EYES = "eyes"
    POSTURE = "posture"
    NECK_STRETCH = "neck_stretch"
    STAND = "stand"
    WATER = "water"
    FULL_BREAK = "full_break"
    WORKOUT = "workout"


class ReminderConfig(BaseModel):
    enabled: bool = True
    interval_min: int
    duration_sec: Optional[int] = None
    active_hours: Optional[list[dict[str, str]]] = None
    align_to_clock: Optional[int] = None
    jitter_min: int = 0


class SehatConfig(BaseModel):
    conditions: list[str] = ["neck_strain", "eye_strain"]
    reminders: dict[str, ReminderConfig]
    quiet_hours: dict[str, str] = {"start": "22:00", "end": "07:00"}
    quiet_ranges: list[dict[str, str]] = [{"start": "22:00", "end": "07:00"}]
    active_days: list[str] = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    level: int = 1
    dnd: bool = False
    auto_close_sec: int = 0
    popup_monitor: str = "primary"


class LogEntry(BaseModel):
    ts: datetime
    event: str
    type: Optional[str] = None
    duration_sec: Optional[int] = None
    total_active_min: Optional[int] = None


class ExerciseInfo(BaseModel):
    id: str
    name: str
    type: str
    level: int
    duration_sec: int
    steps: list[str]
    image: Optional[str] = None
    video_url: Optional[str] = None
    warning: Optional[str] = None


class DailyStats(BaseModel):
    date: str
    total_reminders: int
    done: int
    skipped: int
    snoozed: int
    compliance_pct: float
    active_min: int
    dnd_min: int


class SehatStatus(BaseModel):
    session_active: bool
    session_start: Optional[datetime] = None
    active_min: int = 0
    dnd: bool = False
    next_reminder_type: Optional[str] = None
    next_reminder_in_sec: Optional[int] = None
    today_score: float = 0.0
    today_done: int = 0
    today_total: int = 0
    streak_days: int = 0


if __name__ == "__main__":
    ALL_MODELS = [
        ReminderType, ReminderConfig, SehatConfig, LogEntry,
        ExerciseInfo, DailyStats, SehatStatus,
    ]
    for model in ALL_MODELS:
        if hasattr(model, "model_json_schema"):
            print(f"\n=== {model.__name__} ===")
            print(model.model_json_schema())
        else:
            print(f"\n=== {model.__name__} (enum) ===")
            print([e.value for e in model])
