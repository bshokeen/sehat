"""Tests for sehat.repair_jsonl utility."""

import json
from pathlib import Path

import pytest

from sehat.repair_jsonl import repair_jsonl


@pytest.fixture
def tmp_log(tmp_path):
    return tmp_path / "2026-05-03.jsonl"


def _read_lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class TestRepairJsonl:
    def test_clean_file_unchanged(self, tmp_log):
        good = '{"ts":"2026-05-03T10:00:00","event":"reminder"}\n{"ts":"2026-05-03T10:30:00","event":"done"}\n'
        tmp_log.write_text(good, encoding="utf-8")
        stats = repair_jsonl(tmp_log)
        assert stats["removed"] == 0
        assert stats["split_recovered"] == 0
        assert stats["good_lines"] == 2
        # File content unchanged
        assert tmp_log.read_text(encoding="utf-8") == good

    def test_drops_unrecoverable_truncated_line(self, tmp_log):
        truncated = '{"ts":"2026-05-03T10:00:00","event":"reminder"}\n{"ts":"2026-05-03T10:30:00","ev'  # cut off
        tmp_log.write_text(truncated, encoding="utf-8")
        stats = repair_jsonl(tmp_log)
        assert stats["removed"] == 1
        assert stats["good_lines"] == 1
        rows = _read_lines(tmp_log)
        assert len(rows) == 1
        assert rows[0]["event"] == "reminder"

    def test_splits_concatenated_objects(self, tmp_log):
        # Two JSON objects on one line with no newline between them
        merged = '{"ts":"2026-05-03T10:00:00","event":"a"}{"ts":"2026-05-03T10:01:00","event":"b"}\n'
        tmp_log.write_text(merged, encoding="utf-8")
        stats = repair_jsonl(tmp_log)
        assert stats["split_recovered"] == 2
        rows = _read_lines(tmp_log)
        assert [r["event"] for r in rows] == ["a", "b"]

    def test_skips_empty_lines(self, tmp_log):
        with_empties = '{"ts":"2026-05-03T10:00:00","event":"a"}\n\n\n{"ts":"2026-05-03T10:01:00","event":"b"}\n'
        tmp_log.write_text(with_empties, encoding="utf-8")
        stats = repair_jsonl(tmp_log)
        assert stats["good_lines"] == 2
        assert stats["removed"] == 0  # empties don't count as removed

    def test_dry_run_does_not_write(self, tmp_log):
        bad = '{"ts":"2026-05-03T10:00:00","event":"a"}\n{not_json}\n'
        original = bad
        tmp_log.write_text(bad, encoding="utf-8")
        stats = repair_jsonl(tmp_log, dry_run=True)
        assert stats["removed"] == 1
        # File unchanged on dry-run
        assert tmp_log.read_text(encoding="utf-8") == original

    def test_missing_file_returns_error_dict(self, tmp_path):
        missing = tmp_path / "does_not_exist.jsonl"
        stats = repair_jsonl(missing)
        assert "error" in stats
        assert stats["error"] == "not found"
