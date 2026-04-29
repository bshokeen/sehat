# Changelog

All notable changes to Sehat Health Monitor will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-04-28

### Added
- System tray app with green/yellow/orange/grey heart icons for session states
- 7 reminder types: eyes (20-20-20), posture, neck stretch, standing breaks, water, full breaks, workouts
- 12 built-in exercises with step-by-step instructions and animated illustrations
- Dark-themed exercise popup with Done/Skip buttons and auto-close countdown
- Configurable timers with per-exercise intervals, jitter, clock-aligned triggers, and active hours
- Settings UI accessible from tray menu — edit reminders, active days, quiet hours, and general options
- Quiet hours and active days scheduling
- Snooze support: 15min, 30min, 2hr, or rest-of-day from tray menu
- DND (Do Not Disturb) mode to pause all reminders
- JSONL activity logging with daily log files
- Screen lock detection on Windows — auto-pauses when locked
- Multi-monitor support — popups appear on primary or active monitor
- Hot-reload config — edit config.json while running
- Cross-process snooze state persistence
- PyInstaller build script for standalone Windows executable
- CLI options: `--data-dir`, `--no-auto-start`

[0.1.0]: https://github.com/bshokeen/sehat/releases/tag/v0.1.0
