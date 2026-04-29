"""Tests for Sehat configuration module."""

import json
import shutil
from pathlib import Path

import pytest

from sehat.config import get_data_dir, get_config_path, get_log_dir, get_exercises_dir, get_exercises_index


@pytest.fixture
def tmp_data_dir(tmp_path):
    return tmp_path / "sehat_test"


class TestGetDataDir:
    def test_override_path(self, tmp_path):
        d = get_data_dir(str(tmp_path / "custom"))
        assert d.exists()
        assert d.name == "custom"

    def test_env_var(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SEHAT_DATA_DIR", str(tmp_path / "env_dir"))
        d = get_data_dir()
        assert d.exists()
        assert d.name == "env_dir"

    def test_default_home(self, monkeypatch):
        monkeypatch.delenv("SEHAT_DATA_DIR", raising=False)
        d = get_data_dir()
        assert d.name == ".sehat"


class TestGetConfigPath:
    def test_copies_default_on_first_run(self, tmp_data_dir):
        tmp_data_dir.mkdir(parents=True)
        path = get_config_path(tmp_data_dir)
        assert path.exists()
        cfg = json.loads(path.read_text(encoding="utf-8"))
        assert "reminders" in cfg
        assert "eyes" in cfg["reminders"]

    def test_preserves_existing(self, tmp_data_dir):
        tmp_data_dir.mkdir(parents=True)
        custom = {"reminders": {"eyes": {"enabled": False, "interval_min": 99}}}
        config_path = tmp_data_dir / "config.json"
        config_path.write_text(json.dumps(custom), encoding="utf-8")
        path = get_config_path(tmp_data_dir)
        cfg = json.loads(path.read_text(encoding="utf-8"))
        assert cfg["reminders"]["eyes"]["interval_min"] == 99


class TestGetLogDir:
    def test_creates_log_dir(self, tmp_data_dir):
        tmp_data_dir.mkdir(parents=True)
        log_dir = get_log_dir(tmp_data_dir)
        assert log_dir.exists()
        assert log_dir.name == "logs"


class TestExercisesPaths:
    def test_exercises_dir_exists(self):
        assert get_exercises_dir().exists()

    def test_exercises_index_exists(self):
        assert get_exercises_index().exists()

    def test_exercises_index_valid_json(self):
        data = json.loads(get_exercises_index().read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) > 0
        assert all("id" in e and "type" in e for e in data)
