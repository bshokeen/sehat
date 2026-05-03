"""
Sehat Tray App — standalone health reminder system tray application.

Runs in the Windows/macOS/Linux system tray. Shows exercise popups on timer.
Writes JSONL activity logs to ~/.sehat/logs/.

Usage:
    python -m sehat
    python -m sehat --data-dir /path/to/data
    sehat  (if installed via pip)
"""

VERSION = "1.0.0"

import argparse
import json
import math
import os
import sys
import threading
import time
import tkinter as tk
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import ctypes
import pystray
from PIL import Image, ImageDraw
from plyer import notification

# Set Windows AppUserModelID so notifications show "Sehat" instead of "Python"
if sys.platform == 'win32':
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Sehat.HealthMonitor")

from sehat.timer_engine import TimerEngine
from sehat.config import get_data_dir, get_config_path, get_log_dir, get_exercises_index, get_exercises_dir
from sehat.settings_window import SettingsWindow

# Lock for JSONL writes
_LOG_LOCK = threading.Lock()


# --- Logging ---

def log_event(data_dir: Path, event: str, reminder_type: str = None, **kwargs):
    """Append a log entry to today's JSONL file (thread-safe)."""
    entry = {"ts": datetime.now().isoformat(), "event": event}
    if reminder_type:
        entry["type"] = reminder_type
    entry.update(kwargs)
    line = json.dumps(entry, ensure_ascii=False) + '\n'
    log_dir = get_log_dir(data_dir)
    path = log_dir / f"{date.today().isoformat()}.jsonl"
    with _LOG_LOCK:
        with open(path, 'a', encoding='utf-8') as f:
            f.write(line)
            f.flush()


# --- Tray Icons ---

def create_icon(color: str) -> Image.Image:
    """Create a colored heart icon for systray."""
    size = 64
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    COLORS = {
        'green': (76, 175, 80),
        'yellow': (255, 193, 7),
        'orange': (255, 152, 0),
        'grey': (158, 158, 158),
    }
    rgb = COLORS.get(color, (158, 158, 158))
    try:
        import aggdraw
        dc = aggdraw.Draw(img)
        brush = aggdraw.Brush(rgb)
        path = aggdraw.Path()
        path.moveto(32, 56)
        path.curveto(2, 36, 2, 10, 32, 18)
        path.curveto(62, 10, 62, 36, 32, 56)
        path.close()
        dc.path(path, brush)
        dc.flush()
    except ImportError:
        # Polygon approximation — parametric heart
        pts = []
        for deg in range(360):
            t = math.radians(deg)
            x = 16 * (math.sin(t) ** 3)
            y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
            pts.append((x, y))
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        pad = 2
        sx = (size - 2 * pad) / (max_x - min_x)
        sy = (size - 2 * pad) / (max_y - min_y)
        scale = min(sx, sy)
        cx_off = (size - (max_x - min_x) * scale) / 2
        cy_off = (size - (max_y - min_y) * scale) / 2
        scaled = [(int((p[0] - min_x) * scale + cx_off), int((p[1] - min_y) * scale + cy_off)) for p in pts]
        draw = ImageDraw.Draw(img)
        draw.polygon(scaled, fill=rgb)
    return img


# --- Multi-monitor support ---

def _get_monitor_workarea(monitor_pref: str = "primary") -> tuple[int, int, int, int]:
    """Get the work area (x, y, width, height) for the target monitor."""
    if sys.platform != 'win32':
        return (0, 0, 1920, 1080)
    try:
        user32 = ctypes.windll.user32

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        class RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                        ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", RECT),
                        ("rcWork", RECT), ("dwFlags", ctypes.c_ulong)]

        if monitor_pref == "active":
            pt = POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            hmon = user32.MonitorFromPoint(pt, 2)
        else:
            pt = POINT(0, 0)
            hmon = user32.MonitorFromPoint(pt, 1)

        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        user32.GetMonitorInfoW(hmon, ctypes.byref(mi))
        work = mi.rcWork
        return (work.left, work.top, work.right - work.left, work.bottom - work.top)
    except Exception:
        return (0, 0, 1920, 1080)


# --- Exercise Popup ---

class ExercisePopup:
    """Tkinter popup showing exercise details with Done / Skip buttons and auto-close timer."""

    def __init__(self, root: tk.Tk, exercise: dict, content: str,
                 on_done, on_skip, on_snooze, on_expired=None, auto_close_sec: int = 0,
                 monitor_pref: str = "primary"):
        self._on_expired = on_expired
        self.top = tk.Toplevel(root)
        self.top.overrideredirect(True)
        wx, wy, ww, wh = _get_monitor_workarea(monitor_pref)
        win_w, win_h = 400, 580
        x = wx + ww - win_w - 24
        y = wy + wh - win_h - 60
        self.top.geometry(f"{win_w}x{win_h}+{x}+{y}")
        self.top.configure(bg='#1e1e2e')
        self.top.attributes('-topmost', True)
        self.top.attributes('-alpha', 0.88)
        self.top.resizable(False, False)
        self._auto_close_id = None

        # Drag-to-move
        self._drag_x = 0
        self._drag_y = 0
        def _start_drag(e):
            self._drag_x = e.x
            self._drag_y = e.y
        def _do_drag(e):
            dx = e.x - self._drag_x
            dy = e.y - self._drag_y
            nx = self.top.winfo_x() + dx
            ny = self.top.winfo_y() + dy
            self.top.geometry(f"+{nx}+{ny}")
        self.top.bind('<Button-1>', _start_drag)
        self.top.bind('<B1-Motion>', _do_drag)

        self.top.bind('<Enter>', lambda e: self.top.attributes('-alpha', 1.0))
        self.top.bind('<Leave>', lambda e: self.top.attributes('-alpha', 0.88))

        # Header
        is_neck_critical = exercise.get('id', '') in ('neural_glide_c2c3', 'suboccipital_release')
        header_bg = '#2d1520' if is_neck_critical else '#1e1e2e'
        header = tk.Frame(self.top, bg=header_bg)
        header.pack(fill='x', padx=0, pady=(0, 0))
        if is_neck_critical:
            alert_frame = tk.Frame(header, bg='#f38ba8')
            alert_frame.pack(fill='x')
            tk.Label(
                alert_frame, text='  🔴  NECK — DO THIS NOW  🔴  ',
                font=('Segoe UI', 9, 'bold'), fg='#1e1e2e', bg='#f38ba8'
            ).pack(pady=2)
        name_row = tk.Frame(header, bg=header_bg)
        name_row.pack(fill='x', padx=12, pady=(8, 0))
        name_color = '#f38ba8' if is_neck_critical else '#cdd6f4'
        tk.Label(
            name_row, text=exercise.get('name', ''),
            font=('Segoe UI', 14, 'bold'), fg=name_color, bg=header_bg
        ).pack(side='left')

        # Info line
        level_stars = "⭐" * exercise.get('level', 1)
        dur = exercise.get('duration_sec', 0)
        if dur >= 60:
            dur_text = f"{dur // 60} min" if dur % 60 == 0 else f"{dur // 60}m {dur % 60}s"
        else:
            dur_text = f"{dur}s" if dur else "Quick"
        freq = exercise.get('frequency', '')
        notif_part = f"🔔 {auto_close_sec}s" if auto_close_sec > 0 else ""
        info_parts = [p for p in [level_stars, dur_text, freq, notif_part] if p]
        self._info_var = tk.StringVar(value="  •  ".join(info_parts))
        tk.Label(
            self.top, textvariable=self._info_var,
            font=('Segoe UI', 10), fg='#a6adc8', bg='#1e1e2e'
        ).pack(pady=(0, 6))
        self._info_base_parts = [p for p in [level_stars, dur_text, freq] if p]

        # Animated illustration canvas
        self._canvas = tk.Canvas(self.top, width=380, height=180, bg='#313244',
                                 highlightthickness=0, relief='flat')
        self._canvas.pack(pady=6, padx=16)
        self._anim_frame = 0
        self._exercise_id = exercise.get('id', '')
        self._animate()

        # Warning
        warning = exercise.get('warning')
        if warning:
            tk.Label(
                self.top, text=f"⚠️ {warning}",
                font=('Segoe UI', 9), fg='#f9e2af', bg='#1e1e2e',
                wraplength=360, anchor='w', padx=20
            ).pack(fill='x', pady=(2, 0))

        # Auto-close countdown
        self._countdown_total = auto_close_sec
        self._is_neck_critical = is_neck_critical
        if auto_close_sec > 0:
            self._remaining = float(auto_close_sec)
            self._tick_countdown(on_done)

        # Action buttons
        btn_frame = tk.Frame(self.top, bg='#1e1e2e')
        btn_frame.pack(pady=(8, 8))
        BTN = {'font': ('Segoe UI', 11, 'bold'), 'width': 10, 'relief': 'flat', 'cursor': 'hand2', 'pady': 2}
        tk.Button(btn_frame, text="✅ Done", bg='#a6e3a1', fg='#1e1e2e',
                  command=lambda: self._action(on_done), **BTN).pack(side='left', padx=5)
        tk.Button(btn_frame, text="⏭ Skip", bg='#f38ba8', fg='#1e1e2e',
                  command=lambda: self._action(on_skip), **BTN).pack(side='left', padx=5)

        # Exercise steps from markdown
        steps = []
        tips = []
        if content:
            for line in content.split('\n'):
                stripped = line.strip()
                if stripped.startswith('💡'):
                    tips.append(stripped)
                elif stripped and stripped[0].isdigit() and '. ' in stripped[:5]:
                    steps.append(stripped)

        if steps:
            steps_frame = tk.Frame(self.top, bg='#1e1e2e')
            steps_frame.pack(fill='x', padx=16, pady=(2, 0))
            for step_text in steps[:4]:
                tk.Label(
                    steps_frame, text=step_text, font=('Segoe UI', 9),
                    fg='#cdd6f4', bg='#1e1e2e', anchor='w', justify='left',
                    wraplength=350,
                ).pack(fill='x', pady=1)
            if len(steps) > 4:
                tk.Label(
                    steps_frame, text=f"  … +{len(steps) - 4} more steps",
                    font=('Segoe UI', 8), fg='#6c7086', bg='#1e1e2e', anchor='w',
                ).pack(fill='x')

        if tips:
            for tip_text in tips[:2]:
                tk.Label(
                    self.top, text=tip_text, font=('Segoe UI', 11),
                    fg='#f9e2af', bg='#1e1e2e', anchor='w', justify='left',
                    wraplength=360, padx=20
                ).pack(fill='x', pady=1)

    # ── Animation ─────────────────────────────────────────────

    def _animate(self):
        c = self._canvas
        c.delete('all')
        f = self._anim_frame
        cx, cy = 190, 90
        eid = self._exercise_id

        try:
            if eid == 'eye_20_20_20':
                self._draw_eye_animation(c, f, cx, cy)
            elif eid == 'chin_tucks':
                self._draw_chin_animation(c, f, cx, cy)
            elif eid == 'posture_check':
                self._draw_posture_animation(c, f, cx, cy)
            elif eid == 'shoulder_shrugs':
                self._draw_shoulder_animation(c, f, cx, cy)
            elif eid == 'neck_side_stretch':
                self._draw_neck_stretch_animation(c, f, cx, cy)
            elif eid == 'stand_and_move':
                self._draw_stand_animation(c, f, cx, cy)
            elif eid == 'drink_water':
                self._draw_water_animation(c, f, cx, cy)
            elif eid == 'full_break_stretch':
                self._draw_full_break_animation(c, f, cx, cy)
            elif eid == 'workout_bodyweight':
                self._draw_workout_animation(c, f, cx, cy)
            elif eid == 'workout_stretch_flow':
                self._draw_stretch_flow_animation(c, f, cx, cy)
            elif eid == 'neural_glide_c2c3':
                self._draw_neural_glide_animation(c, f, cx, cy)
            elif eid == 'suboccipital_release':
                self._draw_suboccipital_animation(c, f, cx, cy)
            else:
                c.create_text(cx, cy, text='🏋️', font=('Segoe UI', 36), fill='#6c7086')
        except Exception:
            c.create_text(cx, cy, text='🏋️', font=('Segoe UI', 36), fill='#6c7086')

        self._anim_frame = (f + 1) % 60
        try:
            self._anim_after_id = self.top.after(80, self._animate)
        except tk.TclError:
            pass

    def _draw_eye_animation(self, c: tk.Canvas, f: int, cx: int, cy: int):
        blink_cycle = f % 40
        eye_h = 22 if blink_cycle < 35 else max(2, 22 - (blink_cycle - 35) * 8)
        c.create_oval(cx-40, cy-eye_h, cx+40, cy+eye_h, outline='#e6edf3', width=2)
        if eye_h > 5:
            px = cx + int(12 * math.sin(f * 0.15))
            c.create_oval(px-8, cy-8, px+8, cy+8, fill='#1f6feb', outline='')
            c.create_oval(px-3, cy-3, px+3, cy+3, fill='#0d1117', outline='')
            c.create_oval(px+2, cy-5, px+5, cy-2, fill='white', outline='')
        tx = cx + 120
        pulse = int(3 * math.sin(f * 0.2))
        c.create_oval(tx-10-pulse, 35-pulse, tx+10+pulse, 55+pulse, fill='#238636', outline='')
        c.create_line(cx+40, cy, tx-10, 45, fill='#58a6ff', width=1, dash=(4, 3))
        c.create_text(tx, 70, text='20ft', fill='#8b949e', font=('Segoe UI', 9))
        c.create_text(cx-90, cy, text='👁', font=('Segoe UI', 10), fill='#8b949e')

    def _draw_chin_animation(self, c: tk.Canvas, f: int, cx: int, cy: int):
        offset = int(8 * math.sin(f * 0.12))
        hx = cx + offset
        c.create_oval(hx-22, cy-28, hx+22, cy+20, fill='#cdd6f4', outline='#a6adc8', width=2)
        c.create_oval(hx-10, cy-12, hx-4, cy-6, fill='#1e1e2e', outline='')
        c.create_oval(hx+4, cy-12, hx+10, cy-6, fill='#1e1e2e', outline='')
        c.create_line(hx, cy+20, cx, cy+60, fill='#a6adc8', width=3)
        c.create_line(cx-30, cy+60, cx+30, cy+60, fill='#a6adc8', width=3)
        arrow_x = hx + 35
        c.create_line(arrow_x, cy, arrow_x-15, cy, fill='#89b4fa', width=2, arrow='first')
        c.create_text(arrow_x+20, cy, text='← pull', fill='#89b4fa', font=('Segoe UI', 9))

    def _draw_posture_animation(self, c: tk.Canvas, f: int, cx: int, cy: int):
        t = (math.sin(f * 0.08) + 1) / 2
        slouch = int(20 * (1 - t))
        hx = cx + slouch
        hy = cy - 25 + int(10 * (1 - t))
        c.create_oval(hx-15, hy-15, hx+15, hy+15, fill='#cdd6f4', outline='#a6adc8', width=2)
        spine_mid_x = cx + int(slouch * 0.7)
        spine_mid_y = cy + 10
        c.create_line(hx, hy+15, spine_mid_x, spine_mid_y, cx, cy+50, fill='#a6adc8', width=3, smooth=True)
        c.create_line(spine_mid_x-25, spine_mid_y+5, spine_mid_x+25, spine_mid_y+5, fill='#a6adc8', width=2)
        c.create_rectangle(cx-25, cy+50, cx+25, cy+65, outline='#6c7086', width=2)
        if t > 0.6:
            c.create_text(cx+80, cy-20, text='✓', fill='#a6e3a1', font=('Segoe UI', 14, 'bold'))
        else:
            c.create_text(cx+80, cy-20, text='✗', fill='#f38ba8', font=('Segoe UI', 14, 'bold'))

    def _draw_shoulder_animation(self, c: tk.Canvas, f: int, cx: int, cy: int):
        bounce = int(10 * abs(math.sin(f * 0.15)))
        c.create_oval(cx-16, cy-35, cx+16, cy-5, fill='#cdd6f4', outline='#a6adc8', width=2)
        c.create_line(cx, cy-5, cx, cy+45, fill='#a6adc8', width=3)
        sy = cy + 5 - bounce
        c.create_line(cx-40, sy, cx, cy, fill='#a6adc8', width=3)
        c.create_line(cx+40, sy, cx, cy, fill='#a6adc8', width=3)
        c.create_line(cx-40, sy, cx-35, sy+30, fill='#a6adc8', width=2)
        c.create_line(cx+40, sy, cx+35, sy+30, fill='#a6adc8', width=2)
        if bounce > 5:
            c.create_text(cx-55, sy-10, text='↑', fill='#89b4fa', font=('Segoe UI', 14, 'bold'))
            c.create_text(cx+55, sy-10, text='↑', fill='#89b4fa', font=('Segoe UI', 14, 'bold'))

    def _draw_neck_stretch_animation(self, c: tk.Canvas, f: int, cx: int, cy: int):
        tilt = int(15 * math.sin(f * 0.1))
        c.create_line(cx, cy+10, cx, cy+55, fill='#a6adc8', width=3)
        c.create_line(cx-30, cy+15, cx+30, cy+15, fill='#a6adc8', width=2)
        hx = cx + tilt
        c.create_oval(hx-16, cy-30, hx+16, cy, fill='#cdd6f4', outline='#a6adc8', width=2)
        c.create_line(hx, cy, cx, cy+10, fill='#a6adc8', width=2)
        if abs(tilt) > 8:
            glow_x = hx + (25 if tilt > 0 else -25)
            c.create_text(glow_x, cy-15, text='~', fill='#f9e2af', font=('Segoe UI', 18))

    def _draw_stand_animation(self, c: tk.Canvas, f: int, cx: int, cy: int):
        phase = f % 60
        if phase < 30:
            rise = phase / 30.0
            seat_y = cy + 20 - int(20 * rise)
            c.create_rectangle(cx-60, cy+20, cx-20, cy+55, outline='#6c7086', width=2)
            px = cx - 40 + int(40 * rise)
            c.create_oval(px-12, seat_y-30, px+12, seat_y-6, fill='#cdd6f4', outline='#a6adc8', width=2)
            c.create_line(px, seat_y-6, px, seat_y+25, fill='#a6adc8', width=3)
            c.create_line(px, seat_y+25, px-10, cy+55, fill='#a6adc8', width=2)
            c.create_line(px, seat_y+25, px+10, cy+55, fill='#a6adc8', width=2)
        else:
            walk_f = phase - 30
            wx = cx + int(walk_f * 2.5)
            leg_swing = int(8 * math.sin(walk_f * 0.5))
            c.create_oval(wx-12, cy-30, wx+12, cy-6, fill='#cdd6f4', outline='#a6adc8', width=2)
            c.create_line(wx, cy-6, wx, cy+25, fill='#a6adc8', width=3)
            c.create_line(wx, cy+25, wx-leg_swing, cy+55, fill='#a6adc8', width=2)
            c.create_line(wx, cy+25, wx+leg_swing, cy+55, fill='#a6adc8', width=2)
            c.create_line(wx, cy+5, wx+leg_swing, cy+25, fill='#a6adc8', width=2)
            c.create_line(wx, cy+5, wx-leg_swing, cy+25, fill='#a6adc8', width=2)
            for i in range(3):
                fx = wx - 20 - i * 18
                if fx > cx - 60:
                    c.create_text(fx, cy+58, text='👣', font=('Segoe UI', 7), fill='#6c7086')

    def _draw_water_animation(self, c: tk.Canvas, f: int, cx: int, cy: int):
        gx, gy = cx, cy + 10
        c.create_polygon(gx-25, gy-40, gx+25, gy-40, gx+20, gy+30, gx-20, gy+30,
                         outline='#89b4fa', width=2, fill='')
        level = 0.5 + 0.4 * math.sin(f * 0.08)
        water_top = gy + 30 - int(level * 65)
        ripple = int(3 * math.sin(f * 0.3))
        t = (gy + 30 - water_top) / 70.0
        half_w = 20 + int(t * 5)
        c.create_polygon(
            gx - half_w, water_top + ripple, gx + half_w, water_top - ripple,
            gx + 20, gy + 30, gx - 20, gy + 30,
            fill='#74c7ec', outline='')
        for i in range(3):
            bx = gx - 8 + i * 8
            by = water_top + 10 + int(15 * math.sin(f * 0.2 + i * 2))
            if by < gy + 28:
                r = 2 + (i % 2)
                c.create_oval(bx - r, by - r, bx + r, by + r, fill='#b4befe', outline='')
        if f % 40 < 20:
            dy = gy - 55 + (f % 40) * 2
            c.create_oval(gx - 4, dy - 6, gx + 4, dy + 2, fill='#89b4fa', outline='')
        c.create_text(gx, gy + 48, text='💧 Stay hydrated!', fill='#74c7ec', font=('Segoe UI', 10))

    def _draw_full_break_animation(self, c: tk.Canvas, f: int, cx: int, cy: int):
        h = 180
        c.create_rectangle(0, 0, 380, h, fill='#1e3a5f', outline='')
        sun_y = 22 + int(3 * math.sin(f * 0.05))
        for r in (22, 18, 14):
            alpha_hex = ['#4a5c6f', '#8b7e60', '#f9e2af'][[22, 18, 14].index(r)]
            c.create_oval(310-r, sun_y-r, 310+r, sun_y+r, fill=alpha_hex, outline='')
        for i in range(8):
            angle = math.radians(i * 45 + f * 2)
            rx, ry = 310 + int(28 * math.cos(angle)), sun_y + int(28 * math.sin(angle))
            c.create_line(310, sun_y, rx, ry, fill='#f9e2af', width=1)
        c.create_rectangle(0, 138, 380, h, fill='#2d5016', outline='')
        c.create_rectangle(100, 142, 380, 158, fill='#4a4a3a', outline='')
        for tx in (40, 90, 280, 340):
            c.create_rectangle(tx-3, 90, tx+3, 138, fill='#5c4a32', outline='')
            sway = int(4 * math.sin(f * 0.08 + tx * 0.1))
            c.create_oval(tx-22+sway, 50, tx+22+sway, 95, fill='#2d7a2d', outline='#1a5c1a')
        walk_x = 140 + int((f % 60) * 2.5)
        if walk_x > 350:
            walk_x = 140
        leg = int(8 * math.sin(f * 0.5))
        arm = int(6 * math.sin(f * 0.5))
        py = 92
        c.create_oval(walk_x-9, py-20, walk_x+9, py-2, fill='#cdd6f4', outline='#a6adc8', width=2)
        c.create_line(walk_x, py-2, walk_x, py+22, fill='#a6adc8', width=3)
        c.create_line(walk_x, py+22, walk_x-leg, py+44, fill='#a6adc8', width=2)
        c.create_line(walk_x, py+22, walk_x+leg, py+44, fill='#a6adc8', width=2)
        c.create_line(walk_x, py+6, walk_x+arm, py+22, fill='#a6adc8', width=2)
        c.create_line(walk_x, py+6, walk_x-arm, py+22, fill='#a6adc8', width=2)
        for i in range(3):
            fx = walk_x - 20 - i * 18
            if fx > cx - 60:
                c.create_text(fx, py+56, text='👣', font=('Segoe UI', 7), fill='#6c7086')
        c.create_text(cx, h - 8, text='☕ Take a real break!', fill='#a6e3a1', font=('Segoe UI', 10, 'bold'))

    def _draw_workout_animation(self, c: tk.Canvas, f: int, cx: int, cy: int):
        phase = f % 60
        px = cx
        if phase < 30:
            squat = math.sin(phase * 0.4) * 0.8
            head_y = cy - 28 + int(18 * squat)
            hip_y = cy + 2 + int(18 * squat)
            knee_spread = 12 + int(8 * squat)
            foot_y = cy + 50
            c.create_oval(px-10, head_y-12, px+10, head_y+4, fill='#cdd6f4', outline='#a6adc8', width=2)
            c.create_line(px, head_y+4, px, hip_y, fill='#a6adc8', width=3)
            arm_y = head_y + 16
            c.create_line(px, arm_y, px+25, arm_y - 4 + int(4*squat), fill='#a6adc8', width=2)
            c.create_line(px, arm_y, px-25, arm_y - 4 + int(4*squat), fill='#a6adc8', width=2)
            c.create_line(px, hip_y, px-knee_spread, foot_y, fill='#a6adc8', width=2)
            c.create_line(px, hip_y, px+knee_spread, foot_y, fill='#a6adc8', width=2)
            c.create_line(px-50, foot_y+2, px+50, foot_y+2, fill='#6c7086', width=1)
            c.create_text(px, foot_y + 14, text='Squats', fill='#a6e3a1', font=('Segoe UI', 9))
            reps = int(phase / 6) + 1
            c.create_text(px + 70, cy - 20, text=f'{reps}/5', fill='#6c7086', font=('Segoe UI', 10))
        else:
            pf = phase - 30
            dip = math.sin(pf * 0.4) * 0.7
            body_y = cy + int(16 * dip)
            hand_x1, hand_x2 = px - 35, px + 15
            ground_y = cy + 40
            c.create_line(hand_x1, ground_y, hand_x1 + 5, body_y + 10, fill='#a6adc8', width=2)
            c.create_line(hand_x2, ground_y, hand_x2 - 5, body_y + 10, fill='#a6adc8', width=2)
            c.create_line(px - 40, body_y, px + 40, body_y + 6, fill='#a6adc8', width=3)
            c.create_oval(px - 48, body_y - 10, px - 30, body_y + 6, fill='#cdd6f4', outline='#a6adc8', width=2)
            c.create_line(px + 35, body_y + 6, px + 42, ground_y, fill='#a6adc8', width=2)
            c.create_line(px - 60, ground_y + 2, px + 60, ground_y + 2, fill='#6c7086', width=1)
            c.create_text(px, ground_y + 14, text='Push-ups', fill='#a6e3a1', font=('Segoe UI', 9))
            reps = int(pf / 6) + 1
            c.create_text(px + 70, cy - 20, text=f'{reps}/5', fill='#6c7086', font=('Segoe UI', 10))
        c.create_text(cx, 10, text='💪 Bodyweight Circuit', fill='#f9e2af', font=('Segoe UI', 9))

    def _draw_stretch_flow_animation(self, c: tk.Canvas, f: int, cx: int, cy: int):
        phase = f % 90
        px = cx
        ground_y = cy + 50
        c.create_line(px - 60, ground_y + 2, px + 60, ground_y + 2, fill='#6c7086', width=1)
        if phase < 30:
            tilt = math.sin(phase * 0.25) * 0.8
            head_x = px + int(20 * tilt)
            head_y = cy - 28 + int(abs(tilt) * 6)
            hip_y = cy + 10
            c.create_oval(head_x-9, head_y-11, head_x+9, head_y+5, fill='#cdd6f4', outline='#a6adc8', width=2)
            c.create_line(px, hip_y, head_x, head_y+5, fill='#a6adc8', width=3)
            c.create_line(head_x, head_y+10, head_x + int(20 * tilt), head_y-8, fill='#89b4fa', width=2)
            c.create_line(head_x, head_y+10, px - int(10 * tilt), hip_y + 8, fill='#a6adc8', width=2)
            c.create_line(px, hip_y, px-12, ground_y, fill='#a6adc8', width=2)
            c.create_line(px, hip_y, px+12, ground_y, fill='#a6adc8', width=2)
            c.create_text(px, ground_y + 14, text='Side Bend', fill='#89b4fa', font=('Segoe UI', 9))
        elif phase < 60:
            pf = phase - 30
            bend = math.sin(pf * 0.2) * 0.9
            hip_y = cy + 10
            torso_end_x = px + int(30 * bend)
            torso_end_y = cy - 15 + int(25 * bend)
            c.create_line(px, hip_y, torso_end_x, torso_end_y, fill='#a6adc8', width=3)
            c.create_oval(torso_end_x-8, torso_end_y-14, torso_end_x+8, torso_end_y+2, fill='#cdd6f4', outline='#a6adc8', width=2)
            arm_y = torso_end_y + int(15 * bend)
            c.create_line(torso_end_x, torso_end_y+2, torso_end_x-5, arm_y+10, fill='#a6adc8', width=2)
            c.create_line(torso_end_x, torso_end_y+2, torso_end_x+5, arm_y+10, fill='#a6adc8', width=2)
            c.create_line(px, hip_y, px-12, ground_y, fill='#a6adc8', width=2)
            c.create_line(px, hip_y, px+12, ground_y, fill='#a6adc8', width=2)
            c.create_text(px, ground_y + 14, text='Forward Fold', fill='#89b4fa', font=('Segoe UI', 9))
        else:
            pf = phase - 60
            twist = math.sin(pf * 0.25) * 0.8
            hip_y = cy + 10
            head_y = cy - 26
            c.create_oval(px-9, head_y-11, px+9, head_y+5, fill='#cdd6f4', outline='#a6adc8', width=2)
            c.create_line(px, hip_y, px, head_y+5, fill='#a6adc8', width=3)
            arm_y = cy - 8
            arm_ext = 30
            c.create_line(px, arm_y, px + int(arm_ext * math.cos(twist)), arm_y - int(arm_ext * math.sin(twist)), fill='#89b4fa', width=2)
            c.create_line(px, arm_y, px - int(arm_ext * math.cos(twist)), arm_y + int(arm_ext * math.sin(twist)), fill='#89b4fa', width=2)
            c.create_line(px, hip_y, px-12, ground_y, fill='#a6adc8', width=2)
            c.create_line(px, hip_y, px+12, ground_y, fill='#a6adc8', width=2)
            c.create_text(px, ground_y + 14, text='Seated Twist', fill='#89b4fa', font=('Segoe UI', 9))
        c.create_text(cx, 10, text='🧘 Stretch & Mobility', fill='#f9e2af', font=('Segoe UI', 9))

    def _draw_neural_glide_animation(self, c: tk.Canvas, f: int, cx: int, cy: int):
        phase = f % 50
        tilt = math.sin(phase * math.pi / 50) * 0.35
        px, head_y = cx, cy - 30
        hip_y = cy + 20
        c.create_line(px - 30, hip_y, px + 30, hip_y, fill='#a6adc8', width=3)
        c.create_line(px, hip_y, px, head_y + 15, fill='#a6adc8', width=3)
        hx = px + int(12 * tilt * 3)
        hy = head_y + int(abs(tilt) * 12)
        c.create_oval(hx - 10, hy - 12, hx + 10, hy + 6, fill='#cdd6f4', outline='#a6adc8', width=2)
        arm_ext = 20 + int(30 * abs(tilt) * 3)
        arm_y = hip_y - 8
        c.create_line(px + 30, arm_y, px + 30 + arm_ext, arm_y - 2, fill='#89b4fa', width=2)
        hand_r = 3 + int(3 * abs(tilt) * 3)
        c.create_oval(px + 30 + arm_ext - hand_r, arm_y - 2 - hand_r,
                      px + 30 + arm_ext + hand_r, arm_y - 2 + hand_r, fill='#89b4fa', outline='')
        c.create_line(px - 30, arm_y, px - 40, hip_y + 15, fill='#a6adc8', width=2)
        nerve_alpha = abs(math.sin(phase * math.pi / 25))
        nerve_color = '#bc8cff' if nerve_alpha > 0.3 else '#6c7086'
        c.create_line(hx + 8, hy - 2, px + 20, head_y + 20, fill=nerve_color, width=2, dash=(4, 3))
        c.create_line(px + 20, head_y + 20, px + 30, arm_y, fill=nerve_color, width=2, dash=(4, 3))
        c.create_line(px + 30, arm_y, px + 30 + arm_ext, arm_y - 2, fill=nerve_color, width=2, dash=(4, 3))
        c.create_text(hx + 22, hy - 10, text='C2-C3', fill='#bc8cff', font=('Segoe UI', 8, 'bold'))
        c.create_text(cx, 10, text='🔮 Neural Glide — Right C2-C3', fill='#f9e2af', font=('Segoe UI', 9))

    def _draw_suboccipital_animation(self, c: tk.Canvas, f: int, cx: int, cy: int):
        phase = f % 60
        press = math.sin(phase * math.pi / 30)
        c.create_text(cx, 12, text='🤲 Suboccipital Release — Skull Base', fill='#f9e2af', font=('Segoe UI', 9))
        hx, hy = cx - 15, cy
        head_w, head_h = 34, 40
        c.create_oval(hx - head_w, hy - head_h, hx + head_w, hy + head_h, fill='#cdd6f4', outline='#a6adc8', width=2)
        c.create_oval(hx + 10, hy - 12, hx + 18, hy - 4, fill='#1e1e2e', outline='')
        c.create_line(hx + 14, hy + 10, hx + 24, hy + 8, fill='#a6adc8', width=1)
        c.create_arc(hx + head_w - 4, hy - 8, hx + head_w + 12, hy + 12, start=-90, extent=180, outline='#a6adc8', width=2, style='arc')
        jaw_r = 12 - int(4 * max(0, press))
        c.create_oval(hx + head_w, hy - 2, hx + head_w + jaw_r * 2, hy + jaw_r, fill='#f47067', outline='')
        c.create_text(hx + head_w + jaw_r + 14, hy + 4, text='jaw pain', fill='#f47067', font=('Segoe UI', 8), anchor='w')
        bx = hx - head_w + 6
        by = hy - 6
        pr = 8 + int(5 * max(0, press))
        c.create_oval(bx - pr, by - pr, bx + pr, by + pr, fill='#f0883e', outline='')
        c.create_oval(bx - pr + 4, by - pr + 4, bx + pr - 4, by + pr - 4, fill='#f9e2af', outline='')
        hp = int(3 * max(0, press))
        c.create_line(bx - 40, cy + 45, bx - 10 - hp, by + 8, fill='#8b949e', width=3)
        c.create_oval(bx - 10, by + 2, bx, by + 12, fill='#d4b896', outline='')
        c.create_line(bx + 40, cy + 45, bx + 10 + hp, by + 8, fill='#8b949e', width=3)
        c.create_oval(bx, by + 2, bx + 10, by + 12, fill='#d4b896', outline='')
        c.create_text(bx - 30, by - 16, text='press here', fill='#f0883e', font=('Segoe UI', 9, 'bold'), anchor='e')
        if press > 0.4:
            c.create_text(hx + head_w + 14, hy - 20, text='✓ relief', fill='#a6e3a1', font=('Segoe UI', 8))

    def _action(self, callback):
        if self._auto_close_id:
            self.top.after_cancel(self._auto_close_id)
        if hasattr(self, '_anim_after_id') and self._anim_after_id:
            try:
                self.top.after_cancel(self._anim_after_id)
            except Exception:
                pass
        callback()
        self.top.destroy()

    def _tick_countdown(self, on_done_callback):
        if self._remaining <= 0:
            if self._on_expired:
                self._on_expired()
            self.top.destroy()
            return
        secs = max(0, int(self._remaining + 0.5))
        info_parts = self._info_base_parts + [f"🔔 {secs}s"]
        self._info_var.set("  •  ".join(info_parts))
        self._remaining -= 1
        self._auto_close_id = self.top.after(1000, lambda: self._tick_countdown(on_done_callback))


# --- Main App ---

class SehatTrayApp:
    """Sehat system tray application with timer engine and exercise popups."""

    MIN_POPUP_GAP_SEC = 120

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.session_active = False
        self._session_start: Optional[datetime] = None
        self._active_popup: Optional[ExercisePopup] = None
        self._popup_queue: list[tuple] = []
        self._last_popup_time: float = 0.0

        config_path = get_config_path(data_dir)
        exercises_index = get_exercises_index()
        self.engine = TimerEngine(config_path, exercises_index, self._on_reminder, data_dir=data_dir)

        # Exercise lookup by id
        self.exercises: dict[str, dict] = {}
        if exercises_index.exists():
            for ex in json.loads(exercises_index.read_text(encoding='utf-8')):
                self.exercises[ex['id']] = ex

        self._settings_window: Optional[SettingsWindow] = None

        self.root = tk.Tk()
        self.root.withdraw()

        self.icon = pystray.Icon(
            "sehat",
            create_icon('grey'),
            "Sehat — Health Monitor",
            menu=self._build_menu()
        )

    # ── Menu ─────────────────────────────────────────────────

    def _build_menu(self) -> pystray.Menu:
        snooze_submenu = pystray.Menu(
            pystray.MenuItem("15 Minutes", lambda: self._snooze(15)),
            pystray.MenuItem("30 Minutes", lambda: self._snooze(30)),
            pystray.MenuItem("2 Hours", lambda: self._snooze(120)),
            pystray.MenuItem("Rest of Today", lambda: self._snooze_today()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Resume (clear snooze)", self._clear_snooze,
                             visible=lambda item: self.engine.is_snoozed),
        )
        snooze_remaining = self.engine.get_snooze_remaining_sec()
        snooze_label = "⏰ Snooze"
        if snooze_remaining > 0:
            mins = snooze_remaining // 60
            snooze_label = f"⏰ Snoozed ({mins}m left)"

        try_items = []
        for eid, ex in self.exercises.items():
            label = ex.get('name', eid.replace('_', ' ').title())
            rtype = ex.get('type', eid)
            def _make_try_cb(rt, ei):
                def cb(): self.root.after(0, lambda: self._show_popup(rt, ei))
                return cb
            try_items.append(pystray.MenuItem(label, _make_try_cb(rtype, eid)))
        try_submenu = pystray.Menu(*try_items) if try_items else None

        return pystray.Menu(
            pystray.MenuItem(
                "Start Session", self._start_session,
                visible=lambda item: not self.session_active),
            pystray.MenuItem(
                snooze_label, snooze_submenu,
                visible=lambda item: self.session_active),
            pystray.MenuItem(
                "Pause (DND)", self._toggle_dnd,
                visible=lambda item: self.session_active and not self.engine.is_dnd and not self.engine.is_snoozed),
            pystray.MenuItem(
                "Resume", self._resume_from_dnd,
                visible=lambda item: self.session_active and self.engine.is_dnd),
            pystray.MenuItem(
                "Stop Session", self._stop_session,
                visible=lambda item: self.session_active),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("🎯 Try Exercise", try_submenu,
                             visible=lambda item: try_submenu is not None),
            pystray.MenuItem("⚙️ Settings", lambda: self.root.after(0, self._open_settings)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._quit),
        )

    def _update_tray(self, color: str):
        self.icon.icon = create_icon(color)
        self.icon.menu = self._build_menu()

    # ── Session Controls ─────────────────────────────────────

    def _start_session(self, icon=None, item=None):
        self.session_active = True
        self._session_start = datetime.now()
        self.engine.start()
        self._update_tray('green')
        log_event(self.data_dir, 'session_start')
        try:
            cfg_path = get_config_path(self.data_dir)
            cfg = json.loads(cfg_path.read_text(encoding='utf-8'))
            reminders = cfg.get('reminders', {})
            active_days = cfg.get('active_days', [])
            today = datetime.now().strftime("%a")
            enabled = [f"{k} every {v['interval_min']}min" for k, v in reminders.items() if v.get('enabled')]
            schedule = ', '.join(enabled[:3])
            if len(enabled) > 3:
                schedule += f" +{len(enabled)-3} more"
            if today not in active_days:
                msg = f"⚠️ Today ({today}) not in active days — no reminders will fire."
            else:
                msg = f"Session started! {schedule}"
        except Exception:
            msg = "Health session started. Stay healthy!"
        try:
            notification.notify(title="💚 Sehat Active", message=msg, app_name="Sehat", timeout=5)
        except Exception:
            pass

    def _stop_session(self, icon=None, item=None):
        self.engine.stop()
        active_min = 0
        if self._session_start:
            active_min = int((datetime.now() - self._session_start).total_seconds() / 60)
        self.session_active = False
        self._session_start = None
        self._update_tray('grey')
        log_event(self.data_dir, 'session_end', total_active_min=active_min)

    def _toggle_dnd(self, icon=None, item=None):
        self.engine.set_dnd(True)
        self._update_tray('yellow')
        log_event(self.data_dir, 'dnd_start')

    def _resume_from_dnd(self, icon=None, item=None):
        self.engine.set_dnd(False)
        self._update_tray('green')
        log_event(self.data_dir, 'dnd_end')

    def _snooze(self, duration_min: int):
        self.engine.snooze_all(duration_min)
        self._update_tray('orange')
        log_event(self.data_dir, 'snoozed', duration_min=duration_min)
        try:
            notification.notify(
                title="⏰ Sehat Snoozed",
                message=f"Reminders paused for {duration_min} minutes.",
                app_name="Sehat", timeout=3,
            )
        except Exception:
            pass
        self.root.after(duration_min * 60 * 1000, self._on_snooze_expired)

    def _snooze_today(self):
        now = datetime.now()
        end_of_day = now.replace(hour=23, minute=59, second=59)
        remaining_min = max(1, int((end_of_day - now).total_seconds() / 60))
        self._snooze(remaining_min)

    def _clear_snooze(self, icon=None, item=None):
        self.engine.clear_snooze()
        self._update_tray('green')
        log_event(self.data_dir, 'snooze_cleared')

    def _on_snooze_expired(self):
        if self.session_active and not self.engine.is_dnd and not self.engine.is_snoozed:
            self._update_tray('green')

    def _open_settings(self):
        """Open settings window (prevent duplicates)."""
        if (self._settings_window and self._settings_window.top
                and self._settings_window.top.winfo_exists()):
            self._settings_window.top.lift()
            return
        config_path = get_config_path(self.data_dir)
        self._settings_window = SettingsWindow(
            self.root, config_path, on_save=self._on_settings_saved)

    def _on_settings_saved(self):
        """Called after settings are saved — reseed timer if session is active."""
        if self.session_active:
            self.engine.stop()
            self.engine.start()
            self._update_tray('green')

    def _quit(self, icon=None, item=None):
        if self.session_active:
            self._stop_session()
        self.icon.stop()
        self.root.quit()

    # ── Reminder Callback ────────────────────────────────────

    def _on_reminder(self, reminder_type: str, exercise_id: Optional[str]):
        log_event(self.data_dir, 'reminder', reminder_type)
        self._popup_queue.append((reminder_type, exercise_id))
        self.root.after(0, self._drain_popup_queue)

    def _drain_popup_queue(self):
        if self._active_popup and self._active_popup.top.winfo_exists():
            return
        now = time.time()
        if (now - self._last_popup_time) < self.MIN_POPUP_GAP_SEC and self._popup_queue:
            delay_ms = int((self.MIN_POPUP_GAP_SEC - (now - self._last_popup_time)) * 1000) + 100
            self.root.after(delay_ms, self._drain_popup_queue)
            return
        if not self._popup_queue:
            return
        reminder_type, exercise_id = self._popup_queue.pop(0)
        self._show_popup(reminder_type, exercise_id)

    def _show_popup(self, reminder_type: str, exercise_id: Optional[str]):
        exercise = self.exercises.get(exercise_id, {}) if exercise_id else {}
        if not exercise:
            for eid, ex in self.exercises.items():
                if ex.get('type') == reminder_type:
                    exercise = ex
                    exercise_id = eid
                    break
        name = exercise.get('name', reminder_type.replace('_', ' ').title())

        content = ""
        eid_for_content = exercise_id or exercise.get('id', '')
        if eid_for_content:
            md_path = get_exercises_dir() / f"{eid_for_content}.md"
            if md_path.exists():
                content = md_path.read_text(encoding='utf-8')

        auto_close = 15
        monitor_pref = "primary"
        # Per-reminder activity-duration override (used for the popup's info text)
        activity_dur_override = None
        try:
            cfg_path = get_config_path(self.data_dir)
            cfg = json.loads(cfg_path.read_text(encoding='utf-8'))
            monitor_pref = cfg.get('popup_monitor', 'primary')
            global_auto = cfg.get('auto_close_sec', 0)
            if global_auto > 0:
                auto_close = global_auto
            reminder_cfg = cfg.get('reminders', {}).get(reminder_type, {})
            # Popup-stay override (per reminder type) wins over global
            ps = reminder_cfg.get('popup_stay_sec')
            if isinstance(ps, int) and ps > 0:
                auto_close = ps
            # Activity-duration override (per reminder type) — overrides the
            # exercise's own duration_sec for display in the popup info line.
            ad = reminder_cfg.get('duration_sec')
            if isinstance(ad, int) and ad >= 0:
                activity_dur_override = ad
        except Exception:
            pass

        # Apply activity-duration override to a shallow copy so we don't mutate
        # the exercises dict that other code paths may share.
        if activity_dur_override is not None:
            exercise = dict(exercise)
            exercise['duration_sec'] = activity_dur_override

        def on_done():
            log_event(self.data_dir, 'done', reminder_type,
                      duration_sec=exercise.get('duration_sec', 0))
            self._last_popup_time = time.time()
            self.root.after(1000, self._drain_popup_queue)

        def on_skip():
            log_event(self.data_dir, 'skipped', reminder_type)
            self._last_popup_time = time.time()
            self.root.after(1000, self._drain_popup_queue)

        def on_snooze():
            log_event(self.data_dir, 'snoozed', reminder_type)
            self.engine._last_fired[reminder_type] = time.time()
            self._last_popup_time = time.time()
            self.root.after(1000, self._drain_popup_queue)

        def on_expired():
            log_event(self.data_dir, 'expired', reminder_type)
            self._last_popup_time = time.time()
            self.root.after(1000, self._drain_popup_queue)

        try:
            self._active_popup = ExercisePopup(
                self.root, exercise, content, on_done, on_skip, on_snooze,
                on_expired=on_expired, auto_close_sec=auto_close, monitor_pref=monitor_pref
            )
        except Exception as e:
            print(f"[sehat] ERROR creating popup for {reminder_type}/{exercise_id}: {e}")
            log_event(self.data_dir, 'popup_error', reminder_type, error=str(e))
        self._last_popup_time = time.time()

    # ── Run ──────────────────────────────────────────────────

    def run(self, auto_start: bool = True):
        """Start the app. Tray icon on its own thread, tkinter mainloop on main thread."""
        tray_thread = threading.Thread(target=self.icon.run, daemon=True)
        tray_thread.start()
        if auto_start:
            self.root.after(1500, self._start_session)
        self.root.mainloop()


def main():
    parser = argparse.ArgumentParser(
        prog="sehat",
        description="Sehat Health Monitor — desktop health reminder tray app",
    )
    parser.add_argument(
        "--data-dir", default="",
        help="Data directory for config and logs (default: ~/.sehat/)")
    parser.add_argument(
        "--no-auto-start", action="store_true",
        help="Don't auto-start the session on launch")
    args = parser.parse_args()

    data_dir = get_data_dir(args.data_dir)
    print(f"[sehat] Data directory: {data_dir}")
    print(f"[sehat] Starting tray app (auto-start={'no' if args.no_auto_start else 'yes'})")

    app = SehatTrayApp(data_dir)
    app.run(auto_start=not args.no_auto_start)


if __name__ == "__main__":
    main()
