"""
Sehat Timer Engine — manages reminder schedules.

Runs concurrent reminder timers (eyes, posture, neck_stretch, stand, water, full_break, workout),
each with its own interval from config. Thread-based for tray app compatibility.

Features:
- Hot-reloads config from disk before each cycle
- Respects DND mode (runtime toggle + config flag)
- Respects quiet hours (default 22:00-07:00) and active days
- Picks a random exercise matching type + level when firing
- Fires callbacks in separate threads to avoid blocking the loop
"""

import ctypes
import json
import os
import random
import sys
import threading
import time
from pathlib import Path
from datetime import datetime, time as dtime
from typing import Callable, Optional

from sehat.models import SehatConfig, ReminderConfig, ReminderType

ReminderCallback = Callable[[str, Optional[str]], None]

TICK_INTERVAL_SEC = 10
MIN_BETWEEN_ALERTS_SEC = 300  # 5 minutes between any two alerts


class TimerEngine:
    """Manages multiple concurrent reminder timers with config hot-reload."""

    def __init__(self, config_path: Path, exercises_index_path: Path,
                 callback: ReminderCallback, data_dir: Path = None):
        self.config_path = config_path
        self.exercises_index_path = exercises_index_path
        self.callback = callback
        self._data_dir = data_dir or Path.home() / ".sehat"
        self._running = False
        self._dnd = False
        self._thread: Optional[threading.Thread] = None
        self._last_fired: dict[str, float] = {}
        self._last_any_fired: float = 0.0
        self._lock = threading.Lock()
        self._snooze_until: float = 0.0
        self._snooze_file = self._data_dir / "snooze_state.json"

    # ── Lifecycle ──────────────────────────────────────────────

    def start(self):
        """Start the timer loop in a background thread."""
        if self._running:
            return
        self._running = True
        self._dnd = False
        now = time.time()
        config = self._load_config()
        sorted_types = sorted(t.value for t in ReminderType)
        num_types = len(sorted_types)
        for i, tval in enumerate(sorted_types):
            rcfg = config.reminders.get(tval)
            if rcfg and rcfg.enabled:
                interval_sec = rcfg.interval_min * 60
                offset_sec = interval_sec * (i + 1) / (num_types + 1)
                self._last_fired[tval] = now - interval_sec + offset_sec
            else:
                self._last_fired[tval] = now
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="sehat-timer")
        self._thread.start()

    def stop(self):
        """Stop the timer loop and wait for thread to exit."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    @property
    def running(self) -> bool:
        return self._running

    # ── DND ────────────────────────────────────────────────────

    def set_dnd(self, enabled: bool):
        with self._lock:
            self._dnd = enabled

    @property
    def is_dnd(self) -> bool:
        with self._lock:
            return self._dnd

    # ── Snooze ─────────────────────────────────────────────────

    def snooze_all(self, duration_min: int):
        """Snooze ALL reminders for duration_min minutes."""
        until = time.time() + duration_min * 60
        with self._lock:
            self._snooze_until = until
        self._write_snooze_file(until, duration_min)

    def clear_snooze(self):
        with self._lock:
            self._snooze_until = 0.0
        try:
            if self._snooze_file.exists():
                self._snooze_file.unlink()
        except Exception:
            pass

    @property
    def is_snoozed(self) -> bool:
        with self._lock:
            return time.time() < self._snooze_until

    def get_snooze_remaining_sec(self) -> int:
        with self._lock:
            remaining = self._snooze_until - time.time()
        return int(max(0, remaining))

    def _write_snooze_file(self, until_ts: float, duration_min: int):
        try:
            self._snooze_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "until": datetime.fromtimestamp(until_ts).isoformat(),
                "until_ts": until_ts,
                "duration_min": duration_min,
                "snoozed_at": datetime.now().isoformat(),
            }
            self._snooze_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _check_snooze_file(self):
        try:
            if not self._snooze_file.exists():
                with self._lock:
                    if self._snooze_until > 0:
                        self._snooze_until = 0.0
                return
            data = json.loads(self._snooze_file.read_text(encoding="utf-8"))
            file_ts = data.get("until_ts", 0)
            now = time.time()
            with self._lock:
                if file_ts > now:
                    self._snooze_until = file_ts
                elif file_ts > 0 and file_ts <= now:
                    self._snooze_until = 0.0
                    self._snooze_file.unlink(missing_ok=True)
        except Exception:
            pass

    # ── Config / Data Loading ──────────────────────────────────

    def _load_config(self) -> SehatConfig:
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
            return SehatConfig(**data)
        except Exception:
            default_path = Path(__file__).parent / "default_config.json"
            data = json.loads(default_path.read_text(encoding="utf-8"))
            return SehatConfig(**data)

    def _load_exercises(self) -> list[dict]:
        try:
            return json.loads(self.exercises_index_path.read_text(encoding="utf-8"))
        except Exception:
            return []

    # ── Time Checks ────────────────────────────────────────────

    def _is_quiet_hours(self, config: SehatConfig) -> bool:
        now = datetime.now().time()
        ranges = config.quiet_ranges if config.quiet_ranges else []
        if not ranges and config.quiet_hours:
            ranges = [config.quiet_hours]
        for qr in ranges:
            try:
                start = dtime.fromisoformat(qr.get("start", "22:00"))
                end = dtime.fromisoformat(qr.get("end", "07:00"))
            except (ValueError, TypeError):
                continue
            if start <= end:
                if start <= now <= end:
                    return True
            else:
                if now >= start or now <= end:
                    return True
        return False

    def _is_active_day(self, config: SehatConfig) -> bool:
        day_abbr = datetime.now().strftime("%a")
        return day_abbr in config.active_days

    def _is_in_active_hours(self, rcfg: ReminderConfig) -> bool:
        if not rcfg.active_hours:
            return True
        now = datetime.now().time()
        for window in rcfg.active_hours:
            try:
                start = dtime.fromisoformat(window.get("start", "00:00"))
                end = dtime.fromisoformat(window.get("end", "23:59"))
            except (ValueError, TypeError):
                continue
            if start <= end:
                if start <= now <= end:
                    return True
            else:
                if now >= start or now <= end:
                    return True
        return False

    # ── Exercise Selection ─────────────────────────────────────

    def _pick_exercise(self, reminder_type: str, exercises: list[dict], level: int) -> Optional[str]:
        matching = [
            e for e in exercises
            if e.get("type") == reminder_type and e.get("level", 1) <= level
        ]
        if not matching:
            matching = [e for e in exercises if e.get("type") == reminder_type]
        if matching:
            return random.choice(matching).get("id")
        return None

    # ── Public Query ───────────────────────────────────────────

    def get_next_reminder(self) -> tuple[Optional[str], Optional[int]]:
        config = self._load_config()
        now = time.time()
        next_type: Optional[str] = None
        next_secs: Optional[float] = None

        for rtype, rcfg in config.reminders.items():
            if not rcfg.enabled:
                continue
            last = self._last_fired.get(rtype, now)
            remaining = (rcfg.interval_min * 60) - (now - last)
            if next_secs is None or remaining < next_secs:
                next_secs = remaining
                next_type = rtype

        if next_secs is not None:
            return next_type, int(max(0, next_secs))
        return None, None

    def get_last_fired(self) -> dict[str, float]:
        return dict(self._last_fired)

    def _is_screen_active(self) -> bool:
        """Returns True if screen is on and session is not locked (Windows only)."""
        if sys.platform != 'win32':
            return True
        try:
            user32 = ctypes.windll.user32
            screensaver = ctypes.c_int(0)
            user32.SystemParametersInfoW(0x0072, 0, ctypes.byref(screensaver), 0)
            if screensaver.value:
                return False
            hdesk = user32.OpenInputDesktop(0, False, 0x0001)
            if hdesk:
                user32.CloseDesktop(hdesk)
                return True
            return False
        except Exception:
            return True

    # ── Main Loop ──────────────────────────────────────────────

    def _run_loop(self):
        while self._running:
            try:
                config = self._load_config()
                self._check_snooze_file()

                if (self.is_dnd or config.dnd or self.is_snoozed
                        or self._is_quiet_hours(config) or not self._is_active_day(config)
                        or not self._is_screen_active()):
                    time.sleep(TICK_INTERVAL_SEC)
                    continue

                now = time.time()
                now_dt = datetime.now()
                exercises = self._load_exercises()

                for rtype, rcfg in config.reminders.items():
                    if not rcfg.enabled:
                        continue
                    if not self._is_in_active_hours(rcfg):
                        continue

                    last = self._last_fired.get(rtype, 0.0)
                    interval_sec = rcfg.interval_min * 60
                    should_fire = False

                    if rcfg.align_to_clock is not None:
                        if now_dt.minute == rcfg.align_to_clock and (now - last) >= (interval_sec * 0.8):
                            should_fire = True
                    else:
                        effective_interval = interval_sec
                        if rcfg.jitter_min > 0:
                            jitter_seed = int(last) + hash(rtype)
                            rng = random.Random(jitter_seed)
                            jitter_sec = rng.randint(-rcfg.jitter_min * 60, rcfg.jitter_min * 60)
                            effective_interval = max(interval_sec // 2, interval_sec + jitter_sec)
                        if (now - last) >= effective_interval:
                            should_fire = True

                    if should_fire:
                        if (now - self._last_any_fired) < MIN_BETWEEN_ALERTS_SEC:
                            continue
                        exercise_id = self._pick_exercise(rtype, exercises, config.level)
                        self._last_fired[rtype] = now
                        self._last_any_fired = now
                        threading.Thread(
                            target=self.callback,
                            args=(rtype, exercise_id),
                            daemon=True,
                            name=f"sehat-cb-{rtype}",
                        ).start()
                        break

            except Exception as e:
                print(f"[sehat] Timer error: {e}")

            time.sleep(TICK_INTERVAL_SEC)


# ── Standalone Test ────────────────────────────────────────────

if __name__ == "__main__":
    def on_reminder(rtype: str, exercise_id: Optional[str]):
        print(f"  REMINDER: {rtype} -> exercise: {exercise_id}")

    l_config_path = Path(__file__).parent / "default_config.json"
    l_exercises_path = Path(__file__).parent / "exercises" / "_index.json"

    engine = TimerEngine(l_config_path, l_exercises_path, on_reminder)
    print("Starting timer engine (Ctrl+C to stop)...")
    engine.start()
    try:
        while True:
            ntype, nsec = engine.get_next_reminder()
            print(f"Next: {ntype} in {nsec}s")
            time.sleep(30)
    except KeyboardInterrupt:
        engine.stop()
        print("Stopped.")
