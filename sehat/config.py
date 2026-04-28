"""
Standalone configuration for Sehat Health Monitor.

Data directory layout:
    <data_dir>/
    ├── config.json      ← user configuration (copied from default on first run)
    ├── snooze_state.json ← cross-process snooze state
    └── logs/
        └── YYYY-MM-DD.jsonl  ← daily activity logs

Default data directory: ~/.sehat/
Override with --data-dir CLI argument or SEHAT_DATA_DIR environment variable.
"""

import os
import shutil
from pathlib import Path


def get_data_dir(override: str = "") -> Path:
    """Return the data directory. Priority: override > env var > ~/.sehat/"""
    if override:
        d = Path(override)
    elif os.environ.get("SEHAT_DATA_DIR"):
        d = Path(os.environ["SEHAT_DATA_DIR"])
    else:
        d = Path.home() / ".sehat"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_config_path(data_dir: Path) -> Path:
    """Return config.json path, copying default if it doesn't exist yet."""
    path = data_dir / "config.json"
    if not path.exists():
        default = Path(__file__).parent / "default_config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(default, path)
    return path


def get_log_dir(data_dir: Path) -> Path:
    """Return the logs directory, creating it if needed."""
    d = data_dir / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_exercises_dir() -> Path:
    """Return the bundled exercises directory."""
    return Path(__file__).parent / "exercises"


def get_exercises_index() -> Path:
    """Return path to the exercises _index.json."""
    return get_exercises_dir() / "_index.json"
