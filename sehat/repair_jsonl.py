"""
Repair corrupted Sehat JSONL log files.

Handles:
- Lines truncated mid-JSON (invalid JSON)
- Two JSON objects concatenated on one line (no newline separator)
- Empty lines

Usage:
    python -m sehat.repair_jsonl <path_to_file.jsonl>
    python -m sehat.repair_jsonl <path_to_dir>   # repairs all .jsonl in dir
"""
import json
import re
import sys
from pathlib import Path


def repair_jsonl(path: Path, dry_run: bool = False) -> dict:
    """Repair a single JSONL file. Returns stats dict."""
    if not path.exists():
        return {"file": str(path), "error": "not found"}

    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()

    good: list[str] = []
    removed = 0
    split_fixed = 0

    for i, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue

        # Try parsing as-is
        try:
            json.loads(line)
            good.append(line)
            continue
        except json.JSONDecodeError:
            pass

        # Try splitting concatenated JSON objects: }{ boundary
        parts = re.split(r'(?<=\})\s*(?=\{)', line)
        if len(parts) > 1:
            recovered = 0
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                try:
                    json.loads(part)
                    good.append(part)
                    recovered += 1
                except json.JSONDecodeError:
                    removed += 1
            if recovered > 0:
                split_fixed += recovered
                continue

        # Unrecoverable — drop the line
        print(f"  Line {i}: REMOVED (invalid): {line[:80]}{'...' if len(line) > 80 else ''}")
        removed += 1

    stats = {
        "file": str(path),
        "original_lines": len(lines),
        "good_lines": len(good),
        "removed": removed,
        "split_recovered": split_fixed,
    }

    if not dry_run and (removed > 0 or split_fixed > 0):
        # Write repaired file (atomic: write tmp then replace)
        content = '\n'.join(good) + '\n' if good else ''
        tmp = path.with_suffix('.jsonl.tmp')
        tmp.write_text(content, encoding='utf-8')
        tmp.replace(path)
        print(f"  ✅ Repaired: {path.name}")
    elif removed == 0 and split_fixed == 0:
        print(f"  ✔ Clean: {path.name}")

    return stats


if __name__ == "__main__":
    if len(sys.argv) > 1:
        target = Path(sys.argv[1])
        if target.is_file():
            stats = repair_jsonl(target)
        elif target.is_dir():
            for f in sorted(target.glob("*.jsonl")):
                stats = repair_jsonl(f)
                print(f"    {stats}")
        else:
            print(f"Not found: {target}")
            sys.exit(1)
    else:
        print("Usage: python -m sehat.repair_jsonl <path_to_file_or_dir>")
        sys.exit(1)

    print("\nDone.")
