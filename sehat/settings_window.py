"""
Settings window for Sehat Health Monitor.

Tkinter-based configuration editor. Uses read-modify-write to preserve
fields not shown in the UI (jitter_min, align_to_clock, active_hours, etc.).
"""

import json
import os
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Optional, Callable

from sehat.models import SehatConfig

# Dark theme colors matching the exercise popups
BG = '#1e1e2e'
BG_CARD = '#313244'
FG = '#cdd6f4'
FG_DIM = '#a6adc8'
ACCENT = '#89b4fa'
GREEN = '#a6e3a1'
RED = '#f38ba8'
YELLOW = '#f9e2af'
ENTRY_BG = '#45475a'
ENTRY_FG = '#cdd6f4'

REMINDER_LABELS = {
    'eyes': '👁 Eyes (20-20-20)',
    'posture': '🪑 Posture Reset',
    'water': '💧 Water',
    'neck_stretch': '🦒 Neck Stretch',
    'stand': '🧍 Stand & Move',
    'full_break': '☕ Full Break',
    'workout': '💪 Workout',
}

ALL_DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']


class SettingsWindow:
    """Dark-themed settings editor for Sehat config.json."""

    def __init__(self, root: tk.Tk, config_path: Path,
                 on_save: Optional[Callable] = None):
        self.config_path = config_path
        self.on_save = on_save

        # Load current config as raw dict (read-modify-write)
        self._raw_config = self._load_raw()

        self.top = tk.Toplevel(root)
        self.top.title("⚙️ Sehat Settings")
        self.top.configure(bg=BG)
        self.top.resizable(False, False)
        self.top.attributes('-topmost', True)

        # Center on screen
        win_w, win_h = 540, 680
        sx = root.winfo_screenwidth()
        sy = root.winfo_screenheight()
        x = (sx - win_w) // 2
        y = (sy - win_h) // 2
        self.top.geometry(f"{win_w}x{win_h}+{x}+{y}")

        self.top.grab_set()

        # Scrollable content
        canvas = tk.Canvas(self.top, bg=BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(self.top, orient='vertical', command=canvas.yview)
        self._frame = tk.Frame(canvas, bg=BG)
        self._frame.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.create_window((0, 0), window=self._frame, anchor='nw')
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side='left', fill='both', expand=True, padx=(10, 0), pady=10)
        scrollbar.pack(side='right', fill='y', pady=10)

        # Mouse wheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
        canvas.bind_all('<MouseWheel>', _on_mousewheel)
        self.top.bind('<Destroy>', lambda e: canvas.unbind_all('<MouseWheel>'))

        self._build_ui()

    def _load_raw(self) -> dict:
        try:
            return json.loads(self.config_path.read_text(encoding='utf-8'))
        except Exception:
            default = Path(__file__).parent / "default_config.json"
            return json.loads(default.read_text(encoding='utf-8'))

    # ── UI Construction ──────────────────────────────────────

    def _build_ui(self):
        f = self._frame

        # Title
        tk.Label(f, text="⚙️ Sehat Settings", font=('Segoe UI', 16, 'bold'),
                 fg=FG, bg=BG).pack(pady=(5, 12), anchor='w', padx=8)

        # --- Reminders Section ---
        self._section_label(f, "Reminders")
        self._reminder_vars = {}
        reminders = self._raw_config.get('reminders', {})

        for rtype, label in REMINDER_LABELS.items():
            rcfg = reminders.get(rtype, {})
            row = tk.Frame(f, bg=BG_CARD)
            row.pack(fill='x', pady=2, padx=4)

            enabled_var = tk.BooleanVar(value=rcfg.get('enabled', True))
            tk.Checkbutton(row, variable=enabled_var, bg=BG_CARD,
                           activebackground=BG_CARD, selectcolor=BG_CARD,
                           fg=FG, activeforeground=FG).pack(side='left', padx=(8, 0))
            tk.Label(row, text=label, font=('Segoe UI', 10),
                     fg=FG, bg=BG_CARD, width=20, anchor='w').pack(side='left', padx=(0, 8))

            tk.Label(row, text="every", font=('Segoe UI', 9),
                     fg=FG_DIM, bg=BG_CARD).pack(side='left')
            interval_var = tk.StringVar(value=str(rcfg.get('interval_min', 30)))
            interval_entry = tk.Entry(row, textvariable=interval_var, width=5,
                                      font=('Segoe UI', 10), bg=ENTRY_BG, fg=ENTRY_FG,
                                      insertbackground=FG, relief='flat')
            interval_entry.pack(side='left', padx=3)
            tk.Label(row, text="min", font=('Segoe UI', 9),
                     fg=FG_DIM, bg=BG_CARD).pack(side='left')

            tk.Label(row, text="dur", font=('Segoe UI', 9),
                     fg=FG_DIM, bg=BG_CARD).pack(side='left', padx=(10, 0))
            duration_var = tk.StringVar(value=str(rcfg.get('duration_sec', 0)))
            duration_entry = tk.Entry(row, textvariable=duration_var, width=5,
                                      font=('Segoe UI', 10), bg=ENTRY_BG, fg=ENTRY_FG,
                                      insertbackground=FG, relief='flat')
            duration_entry.pack(side='left', padx=3)
            tk.Label(row, text="sec", font=('Segoe UI', 9),
                     fg=FG_DIM, bg=BG_CARD).pack(side='left', padx=(0, 8))

            self._reminder_vars[rtype] = {
                'enabled': enabled_var,
                'interval_min': interval_var,
                'duration_sec': duration_var,
            }

        # --- Active Days ---
        self._section_label(f, "Active Days")
        days_frame = tk.Frame(f, bg=BG)
        days_frame.pack(fill='x', padx=8, pady=4)
        active_days = self._raw_config.get('active_days', ALL_DAYS)
        self._day_vars = {}
        for day in ALL_DAYS:
            var = tk.BooleanVar(value=day in active_days)
            self._day_vars[day] = var
            tk.Checkbutton(days_frame, text=day, variable=var, bg=BG,
                           activebackground=BG, selectcolor=BG_CARD,
                           fg=FG, activeforeground=FG,
                           font=('Segoe UI', 10)).pack(side='left', padx=4)

        # --- Quiet Hours ---
        self._section_label(f, "Quiet Hours (no reminders)")
        quiet_frame = tk.Frame(f, bg=BG)
        quiet_frame.pack(fill='x', padx=8, pady=4)
        quiet_ranges = self._raw_config.get('quiet_ranges', [{"start": "22:00", "end": "07:00"}])
        first_range = quiet_ranges[0] if quiet_ranges else {"start": "22:00", "end": "07:00"}

        tk.Label(quiet_frame, text="From", font=('Segoe UI', 10),
                 fg=FG_DIM, bg=BG).pack(side='left')
        self._quiet_start = tk.StringVar(value=first_range.get('start', '22:00'))
        tk.Entry(quiet_frame, textvariable=self._quiet_start, width=6,
                 font=('Segoe UI', 10), bg=ENTRY_BG, fg=ENTRY_FG,
                 insertbackground=FG, relief='flat').pack(side='left', padx=4)
        tk.Label(quiet_frame, text="to", font=('Segoe UI', 10),
                 fg=FG_DIM, bg=BG).pack(side='left')
        self._quiet_end = tk.StringVar(value=first_range.get('end', '07:00'))
        tk.Entry(quiet_frame, textvariable=self._quiet_end, width=6,
                 font=('Segoe UI', 10), bg=ENTRY_BG, fg=ENTRY_FG,
                 insertbackground=FG, relief='flat').pack(side='left', padx=4)
        tk.Label(quiet_frame, text="(HH:MM)", font=('Segoe UI', 9),
                 fg=FG_DIM, bg=BG).pack(side='left', padx=4)

        # --- General Settings ---
        self._section_label(f, "General")
        gen_frame = tk.Frame(f, bg=BG)
        gen_frame.pack(fill='x', padx=8, pady=4)

        # Auto-close
        row1 = tk.Frame(gen_frame, bg=BG)
        row1.pack(fill='x', pady=3)
        tk.Label(row1, text="Auto-close popup after", font=('Segoe UI', 10),
                 fg=FG, bg=BG).pack(side='left')
        self._auto_close_var = tk.StringVar(
            value=str(self._raw_config.get('auto_close_sec', 20)))
        tk.Entry(row1, textvariable=self._auto_close_var, width=5,
                 font=('Segoe UI', 10), bg=ENTRY_BG, fg=ENTRY_FG,
                 insertbackground=FG, relief='flat').pack(side='left', padx=4)
        tk.Label(row1, text="seconds (0 = manual)", font=('Segoe UI', 9),
                 fg=FG_DIM, bg=BG).pack(side='left')

        # Popup monitor
        row2 = tk.Frame(gen_frame, bg=BG)
        row2.pack(fill='x', pady=3)
        tk.Label(row2, text="Show popup on", font=('Segoe UI', 10),
                 fg=FG, bg=BG).pack(side='left')
        self._monitor_var = tk.StringVar(
            value=self._raw_config.get('popup_monitor', 'primary'))
        for val in ('primary', 'active'):
            tk.Radiobutton(row2, text=val.title(), variable=self._monitor_var,
                           value=val, bg=BG, activebackground=BG,
                           selectcolor=BG_CARD, fg=FG, activeforeground=FG,
                           font=('Segoe UI', 10)).pack(side='left', padx=6)

        # Level
        row3 = tk.Frame(gen_frame, bg=BG)
        row3.pack(fill='x', pady=3)
        tk.Label(row3, text="Exercise level", font=('Segoe UI', 10),
                 fg=FG, bg=BG).pack(side='left')
        self._level_var = tk.StringVar(
            value=str(self._raw_config.get('level', 1)))
        tk.Entry(row3, textvariable=self._level_var, width=4,
                 font=('Segoe UI', 10), bg=ENTRY_BG, fg=ENTRY_FG,
                 insertbackground=FG, relief='flat').pack(side='left', padx=4)
        tk.Label(row3, text="(1 = easiest)", font=('Segoe UI', 9),
                 fg=FG_DIM, bg=BG).pack(side='left')

        # --- Buttons ---
        btn_frame = tk.Frame(f, bg=BG)
        btn_frame.pack(pady=(16, 8))
        BTN = {'font': ('Segoe UI', 11, 'bold'), 'width': 12, 'relief': 'flat',
               'cursor': 'hand2', 'pady': 4}
        tk.Button(btn_frame, text="💾 Save", bg=GREEN, fg='#1e1e2e',
                  command=self._save, **BTN).pack(side='left', padx=8)
        tk.Button(btn_frame, text="Cancel", bg='#585b70', fg=FG,
                  command=self.top.destroy, **BTN).pack(side='left', padx=8)

        # Config file path hint
        tk.Label(f, text=f"📁 {self.config_path}", font=('Segoe UI', 8),
                 fg=FG_DIM, bg=BG, wraplength=500).pack(pady=(4, 8), padx=8, anchor='w')

    def _section_label(self, parent, text: str):
        tk.Label(parent, text=text, font=('Segoe UI', 12, 'bold'),
                 fg=ACCENT, bg=BG).pack(pady=(12, 4), anchor='w', padx=8)

    # ── Save (read-modify-write) ─────────────────────────────

    def _save(self):
        # Validate inputs
        errors = []
        for rtype, vars_ in self._reminder_vars.items():
            try:
                val = int(vars_['interval_min'].get())
                if val < 1:
                    errors.append(f"{rtype}: interval must be >= 1 minute")
            except ValueError:
                errors.append(f"{rtype}: interval must be a number")
            try:
                val = int(vars_['duration_sec'].get())
                if val < 0:
                    errors.append(f"{rtype}: duration must be >= 0")
            except ValueError:
                errors.append(f"{rtype}: duration must be a number")

        # Validate quiet hours
        for label, var in [("Quiet start", self._quiet_start), ("Quiet end", self._quiet_end)]:
            val = var.get().strip()
            if val:
                parts = val.split(':')
                if len(parts) != 2:
                    errors.append(f"{label}: use HH:MM format")
                else:
                    try:
                        h, m = int(parts[0]), int(parts[1])
                        if not (0 <= h <= 23 and 0 <= m <= 59):
                            errors.append(f"{label}: invalid time")
                    except ValueError:
                        errors.append(f"{label}: use HH:MM format")

        try:
            level = int(self._level_var.get())
            if level < 1:
                errors.append("Level must be >= 1")
        except ValueError:
            errors.append("Level must be a number")

        try:
            ac = int(self._auto_close_var.get())
            if ac < 0:
                errors.append("Auto-close must be >= 0")
        except ValueError:
            errors.append("Auto-close must be a number")

        if errors:
            messagebox.showerror("Invalid Settings", "\n".join(errors), parent=self.top)
            return

        # Read-modify-write: start from current raw config
        cfg = self._raw_config.copy()
        reminders = cfg.get('reminders', {})
        for rtype, vars_ in self._reminder_vars.items():
            if rtype not in reminders:
                reminders[rtype] = {}
            reminders[rtype]['enabled'] = vars_['enabled'].get()
            reminders[rtype]['interval_min'] = int(vars_['interval_min'].get())
            reminders[rtype]['duration_sec'] = int(vars_['duration_sec'].get())
            # Preserve existing jitter_min, align_to_clock, active_hours untouched
        cfg['reminders'] = reminders

        cfg['active_days'] = [d for d in ALL_DAYS if self._day_vars[d].get()]

        qs = self._quiet_start.get().strip()
        qe = self._quiet_end.get().strip()
        if qs and qe:
            cfg['quiet_ranges'] = [{"start": qs, "end": qe}]

        cfg['auto_close_sec'] = int(self._auto_close_var.get())
        cfg['popup_monitor'] = self._monitor_var.get()
        cfg['level'] = int(self._level_var.get())

        # Validate the merged config with pydantic
        try:
            SehatConfig(**cfg)
        except Exception as e:
            messagebox.showerror("Config Validation Error", str(e), parent=self.top)
            return

        # Atomic write: write to temp file, then rename
        tmp_path = self.config_path.with_suffix('.tmp')
        try:
            tmp_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding='utf-8')
            tmp_path.replace(self.config_path)
        except Exception as e:
            messagebox.showerror("Save Error", f"Could not save config:\n{e}", parent=self.top)
            return

        if self.on_save:
            self.on_save()

        self.top.destroy()
