# Sehat Health Monitor 💚

A standalone desktop health reminder app that lives in your system tray. Configurable timers for eye breaks, posture checks, neck stretches, hydration, and more — with animated exercise popups and activity logging.

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![Platform](https://img.shields.io/badge/platform-Windows-green)
![License](https://img.shields.io/badge/license-MIT-brightgreen)

## Features

- **System tray icon** — green heart when active, yellow when paused, orange when snoozed, grey when stopped
- **7 reminder types** — eyes (20-20-20), posture, neck stretches, standing breaks, water, full breaks, workouts
- **12 built-in exercises** — each with step-by-step instructions, animated illustrations, tips, and warnings
- **Animated popups** — dark-themed, draggable, auto-closing exercise popups with Done/Skip buttons
- **Configurable timers** — per-exercise intervals, jitter, clock-aligned triggers, active hours windows
- **Quiet hours** — auto-pause reminders during sleep hours or non-active days
- **Snooze** — 15min, 30min, 2hr, or rest-of-day snooze from the tray menu
- **DND mode** — pause all reminders without stopping the session
- **Activity logging** — JSONL logs of all events (reminders, done, skipped, snoozed)
- **Screen lock detection** — auto-pauses when screen is locked or off (Windows)
- **Multi-monitor support** — popups appear on primary or active monitor
- **Hot-reload config** — edit `config.json` while running; changes take effect on the next timer cycle

## Quick Start

```bash
# Install
pip install -r requirements.txt

# Run
python -m sehat
```

The app starts in the system tray with a grey heart icon. It auto-starts a health session — the icon turns green and reminders begin firing at their configured intervals.

## Installation

### From source

```bash
git clone <this-repo>
cd sehat-health-monitor
pip install -r requirements.txt
python -m sehat
```

### As a package

```bash
pip install .
sehat
```

## Configuration

On first run, Sehat copies `default_config.json` to `~/.sehat/config.json`. Edit this file to customize:

```json
{
  "reminders": {
    "eyes":         { "enabled": true, "interval_min": 20, "duration_sec": 20, "jitter_min": 5 },
    "posture":      { "enabled": true, "interval_min": 30, "duration_sec": 15, "jitter_min": 5 },
    "water":        { "enabled": true, "interval_min": 60, "duration_sec": 10, "align_to_clock": 55 },
    "neck_stretch": { "enabled": true, "interval_min": 45, "duration_sec": 90 },
    "stand":        { "enabled": true, "interval_min": 60, "duration_sec": 180 },
    "full_break":   { "enabled": true, "interval_min": 120, "duration_sec": 600 },
    "workout":      { "enabled": true, "interval_min": 240, "duration_sec": 1800,
                      "active_hours": [{"start": "06:00", "end": "09:00"}, {"start": "17:00", "end": "21:00"}] }
  },
  "quiet_ranges": [{ "start": "22:00", "end": "07:00" }],
  "active_days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
  "level": 1,
  "dnd": false,
  "auto_close_sec": 20,
  "popup_monitor": "primary"
}
```

### Config Options

| Option | Description |
|--------|-------------|
| `interval_min` | Minutes between reminders of this type |
| `duration_sec` | Suggested exercise duration (shown in popup) |
| `jitter_min` | Random ± offset to avoid mechanical feel |
| `align_to_clock` | Fire at this minute of the hour (e.g., 55 → :55) |
| `active_hours` | Time windows when this reminder is active |
| `quiet_ranges` | Global quiet hours (no reminders fire) |
| `active_days` | Days of week when reminders are active |
| `level` | Exercise difficulty level (1 = easiest) |
| `auto_close_sec` | Auto-close popup after N seconds (0 = manual close) |
| `popup_monitor` | `"primary"` or `"active"` (monitor with cursor) |

## CLI Options

```bash
python -m sehat                      # Default: data in ~/.sehat/, auto-start session
python -m sehat --data-dir ./mydata  # Custom data directory
python -m sehat --no-auto-start      # Start in tray but don't begin session
```

You can also set `SEHAT_DATA_DIR` environment variable instead of `--data-dir`.

## Tray Menu

Right-click the tray icon:

| Item | When Visible | Action |
|------|-------------|--------|
| **Start Session** | Session stopped | Start reminder timers |
| **⏰ Snooze** | Session active | Submenu: 15min / 30min / 2hr / Rest of Today / Resume |
| **Pause (DND)** | Session active, not paused | Pause all reminders |
| **Resume** | Session paused | Resume reminders |
| **Stop Session** | Session active | Stop all timers |
| **🎯 Try Exercise** | Always | Preview any exercise popup on demand |
| **Quit** | Always | Stop session and exit |

## Built-in Exercises

| Exercise | Type | Duration | Description |
|----------|------|----------|-------------|
| 20-20-20 Eye Break | eyes | 20s | Look 20ft away for 20 seconds |
| Posture Reset | posture | 15s | Sit back, shoulders down, ears over shoulders |
| Chin Tucks | neck_stretch | 60s | Draw chin backward, strengthen deep neck flexors |
| Shoulder Shrugs & Rolls | neck_stretch | 45s | Shrug up, hold, release; roll forward and back |
| Neck Side Stretch | neck_stretch | 90s | Gentle ear-to-shoulder tilt each side |
| Neural Glide — C2-C3 | neck_stretch | 60s | Nerve mobility exercise for cervical issues |
| Suboccipital Release | neck_stretch | 120s | Self-massage at skull base for jaw/ear pain |
| Stand & Move | stand | 3min | Walk, calf raises, hip circles |
| Drink Water 💧 | water | instant | Hydration reminder |
| Full Break — Walk & Stretch | full_break | 10min | Leave desk, full-body stretch, deep breathing |
| Quick Bodyweight Workout | workout | 15min | Squats, push-ups, lunges, plank circuit |
| Stretch & Mobility Flow | workout | 10min | Full-body stretch routine |

## Data Directory

```
~/.sehat/
├── config.json          ← your configuration
├── snooze_state.json    ← cross-process snooze state (auto-managed)
└── logs/
    └── 2026-04-08.jsonl ← daily activity log
```

### Log Format (JSONL)

```json
{"ts": "2026-04-08T10:30:00", "event": "session_start"}
{"ts": "2026-04-08T10:50:00", "event": "reminder", "type": "eyes"}
{"ts": "2026-04-08T10:50:15", "event": "done", "type": "eyes", "duration_sec": 20}
{"ts": "2026-04-08T11:20:00", "event": "reminder", "type": "posture"}
{"ts": "2026-04-08T11:20:08", "event": "skipped", "type": "posture"}
```

## Dependencies

| Package | Purpose |
|---------|---------|
| [pystray](https://pypi.org/project/pystray/) | System tray icon and menu |
| [Pillow](https://pypi.org/project/Pillow/) | Icon rendering |
| [plyer](https://pypi.org/project/plyer/) | Desktop notifications |
| [pydantic](https://pypi.org/project/pydantic/) | Config/model validation |

Optional: `aggdraw` for smoother heart icon rendering (falls back to polygon approximation).

## Adding Custom Exercises

1. Add a JSON entry to `sehat/exercises/_index.json`
2. Create a matching `sehat/exercises/your_exercise.md` with Steps / Tips / Why It Helps sections
3. Optionally add an animation method in `tray_app.py` → `ExercisePopup._animate()`

## Platform Support

- **Windows** — full support (system tray, screen lock detection, multi-monitor, notifications)
- **macOS / Linux** — tray icon and popups work; screen lock detection falls back to always-active

## License

MIT
