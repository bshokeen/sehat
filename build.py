"""
Build script for Sehat Health Monitor — creates a standalone Windows executable.

Usage:
    python build.py

Output:
    dist/sehat/  — folder containing sehat.exe and all dependencies
    dist/sehat.zip — zipped distribution ready for sharing
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Fix Windows console encoding for emoji/unicode
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')


ROOT = Path(__file__).parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
APP_NAME = "sehat"


def build():
    print("=" * 60)
    print("  Sehat Health Monitor — Build")
    print("=" * 60)

    # Ensure PyInstaller is available
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("[build] Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install",
                               "pyinstaller", "--quiet"])

    # Clean previous build
    for d in (DIST, BUILD):
        if d.exists():
            print(f"[build] Cleaning {d}")
            shutil.rmtree(d)

    # Collect data files
    exercises_dir = ROOT / "sehat" / "exercises"
    data_args = []

    # Default config
    data_args += ["--add-data", f"{ROOT / 'sehat' / 'default_config.json'};sehat"]

    # Exercises directory (json, md, images)
    data_args += ["--add-data", f"{exercises_dir};sehat/exercises"]

    # Hidden imports that PyInstaller may miss
    hidden = [
        "pystray._win32",
        "plyer.platforms.win",
        "plyer.platforms.win.notification",
        "PIL",
        "pydantic",
    ]
    hidden_args = []
    for h in hidden:
        hidden_args += ["--hidden-import", h]

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--noconfirm",
        "--windowed",
        "--onedir",
        "--clean",
        *data_args,
        *hidden_args,
        str(ROOT / "sehat" / "__main__.py"),
    ]

    print(f"[build] Running PyInstaller...")
    print(f"[build] Command: {' '.join(cmd[:6])} ...")
    result = subprocess.run(cmd, cwd=str(ROOT))

    if result.returncode != 0:
        print("[build] ❌ Build failed!")
        sys.exit(1)

    exe_path = DIST / APP_NAME / f"{APP_NAME}.exe"
    if exe_path.exists():
        print(f"[build] ✅ Build successful!")
        print(f"[build] Executable: {exe_path}")
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"[build] Size: {size_mb:.1f} MB")
    else:
        print("[build] ❌ Executable not found after build!")
        sys.exit(1)

    # Create zip for distribution
    zip_path = DIST / APP_NAME
    print(f"[build] Creating zip: {zip_path}.zip")
    shutil.make_archive(str(zip_path), 'zip', str(DIST), APP_NAME)
    zip_size = (DIST / f"{APP_NAME}.zip").stat().st_size / (1024 * 1024)
    print(f"[build] Zip size: {zip_size:.1f} MB")
    print()
    print(f"[build] Distribution ready:")
    print(f"  Folder: {DIST / APP_NAME}")
    print(f"  Zip:    {DIST / APP_NAME}.zip")


if __name__ == "__main__":
    build()
