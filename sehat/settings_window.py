"""
Settings window for Sehat.

Compact, borderless Tkinter editor for the sehat tray.

Three independent reminder concepts (kept separate so they don't conflate):
  1. interval_min     — how often a reminder fires
  2. popup_stay_sec   — how long the popup stays before auto-dismiss
                        (per-reminder; falls back to global auto_close_sec)
  3. duration_sec     — how long the actual exercise takes (informational
                        on the popup; overrides the exercise's own value
                        when set)

Other design choices:
* No native title bar — replaced with a custom top bar that holds the title
  plus 💾 Save and ✕ Close icons.
* Quiet hours use a draggable 24-hour timeline canvas instead of two
  abstract sliders.
"""

import json
import re
import tkinter as tk
from tkinter import messagebox
from pathlib import Path
from typing import Optional, Callable

from sehat.models import SehatConfig

# Catppuccin-style dark palette (matches the exercise popups)
BG = '#1e1e2e'
BG_CARD = '#313244'
BG_TOPBAR = '#181825'
FG = '#cdd6f4'
FG_DIM = '#a6adc8'
FG_HINT = '#7f849c'
ACCENT = '#89b4fa'
GREEN = '#a6e3a1'
GREEN_DIM = '#3a5a4a'  # muted green for the active-hours background bar
MAUVE = '#cba6f7'      # purple — used for the quiet-hours block (sleep/night)
RED = '#f38ba8'
YELLOW = '#f9e2af'
ENTRY_BG = '#45475a'
ENTRY_FG = '#cdd6f4'
ERR_BG = '#f38ba8'

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

MONITOR_OPTIONS = [
    ("Main monitor", "primary"),
    ("Where my mouse is", "active"),
]

DEFAULT_CONFIG_PATH = Path(__file__).parent / "default_config.json"

TIME_RE = re.compile(r'^([01]\d|2[0-3]):([0-5]\d)$')


def _coerce_int_str(value, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _split_hhmm(hhmm: str) -> tuple:
    """Parse 'HH:MM' into (hour, minute), defaulting to (0, 0) on error."""
    try:
        h, m = hhmm.strip().split(':')
        return max(0, min(23, int(h))), max(0, min(59, int(m)))
    except (ValueError, AttributeError):
        return 0, 0


class SettingsWindow:
    """Borderless dark-themed settings editor for Sehat config.json."""

    def __init__(self, root: tk.Tk, config_path: Path,
                 on_save: Optional[Callable] = None):
        self.config_path = config_path
        self.on_save = on_save

        self._raw_config = self._load_raw()
        self._defaults = self._load_defaults()
        self._original_reminders = set(self._raw_config.get('reminders', {}).keys())

        self.top = tk.Toplevel(root)
        self.top.title("Sehat Settings")  # taskbar tooltip only
        # Outer color acts as a visible 2px border around the borderless window
        self.top.configure(bg=ACCENT)
        self.top.overrideredirect(True)   # remove native title bar
        self.top.resizable(False, False)
        self.top.attributes('-topmost', True)

        # Esc closes (safety net since we hid the OS Close button)
        self.top.bind('<Escape>', lambda e: self.top.destroy())

        # Centre on screen (provisional — re-set later after auto-sizing to content)
        win_w, win_h = 600, 580
        sx = root.winfo_screenwidth()
        sy = root.winfo_screenheight()
        x = (sx - win_w) // 2
        y = (sy - win_h) // 2
        self.top.geometry(f"{win_w}x{win_h}+{x}+{y}")
        self._win_w = win_w

        # Inner container — sits inside the 2px ACCENT border above
        self._inner = tk.Frame(self.top, bg=BG)
        self._inner.pack(fill='both', expand=True, padx=2, pady=2)

        self.top.grab_set()

        self._build_topbar()
        self._build_body()

        # Auto-size window to fit content, then centre on screen.
        # No scroll needed — every section is visible at once.
        self.top.update_idletasks()
        content_w = self._inner.winfo_reqwidth() + 4   # +4 for the 2px border
        content_h = self._inner.winfo_reqheight() + 4
        sx = root.winfo_screenwidth()
        sy = root.winfo_screenheight()
        x = max(0, (sx - content_w) // 2)
        y = max(0, (sy - content_h) // 2)
        self.top.geometry(f"{content_w}x{content_h}+{x}+{y}")

        self.top.focus_set()

    def _load_raw(self) -> dict:
        try:
            return json.loads(self.config_path.read_text(encoding='utf-8'))
        except Exception:
            return json.loads(DEFAULT_CONFIG_PATH.read_text(encoding='utf-8'))

    def _load_defaults(self) -> dict:
        try:
            return json.loads(DEFAULT_CONFIG_PATH.read_text(encoding='utf-8'))
        except Exception:
            return {}

    # ── Custom top bar ────────────────────────────────────────

    def _build_topbar(self):
        bar = tk.Frame(self._inner, bg=BG_TOPBAR, height=44)
        bar.pack(fill='x', side='top')
        bar.pack_propagate(False)

        title = tk.Label(bar, text="⚙️  Sehat Settings",
                         font=('Segoe UI', 12, 'bold'),
                         fg=FG, bg=BG_TOPBAR)
        title.pack(side='left', padx=14)

        # Right-side icon buttons (rightmost = close)
        close_btn = tk.Label(bar, text='✕', font=('Segoe UI', 13, 'bold'),
                             fg=FG_DIM, bg=BG_TOPBAR, padx=12, cursor='hand2')
        close_btn.pack(side='right', padx=(2, 8))
        close_btn.bind('<Enter>', lambda e: close_btn.configure(fg=RED, bg='#3a2030'))
        close_btn.bind('<Leave>', lambda e: close_btn.configure(fg=FG_DIM, bg=BG_TOPBAR))
        close_btn.bind('<Button-1>', lambda e: self.top.destroy())

        save_btn = tk.Label(bar, text='💾', font=('Segoe UI', 13),
                            fg=GREEN, bg=BG_TOPBAR, padx=12, cursor='hand2')
        save_btn.pack(side='right', padx=(2, 2))
        save_btn.bind('<Enter>', lambda e: save_btn.configure(bg='#1f3a2a'))
        save_btn.bind('<Leave>', lambda e: save_btn.configure(bg=BG_TOPBAR))
        save_btn.bind('<Button-1>', lambda e: self._save())

        reset_btn = tk.Label(bar, text='↺', font=('Segoe UI', 14, 'bold'),
                             fg=YELLOW, bg=BG_TOPBAR, padx=12, cursor='hand2')
        reset_btn.pack(side='right', padx=(2, 2))
        reset_btn.bind('<Enter>', lambda e: reset_btn.configure(bg='#3a3520'))
        reset_btn.bind('<Leave>', lambda e: reset_btn.configure(bg=BG_TOPBAR))
        reset_btn.bind('<Button-1>', lambda e: self._reset_to_defaults())

        # Make the title area draggable so the borderless window can be moved.
        for w in (bar, title):
            w.bind('<Button-1>', self._drag_start)
            w.bind('<B1-Motion>', self._drag_move)

    def _drag_start(self, event):
        self._drag_offset_x = event.x_root - self.top.winfo_x()
        self._drag_offset_y = event.y_root - self.top.winfo_y()

    def _drag_move(self, event):
        x = event.x_root - self._drag_offset_x
        y = event.y_root - self._drag_offset_y
        self.top.geometry(f"+{x}+{y}")

    # ── Body ──────────────────────────────────────────────────

    def _build_body(self):
        # No scrollbar — we auto-size the window to fit content (see __init__)
        f = tk.Frame(self._inner, bg=BG)
        f.pack(fill='both', expand=True, padx=10, pady=(2, 8))
        self._frame = f

        # --- Reminders ---
        self._section_label(f, "Reminders", None)
        self._reminder_vars = {}
        reminders = self._raw_config.get('reminders', {})
        default_reminders = self._defaults.get('reminders', {})
        # Effective global popup-visible default (used to pre-fill blank rows
        # so users SEE what's actually in effect, not an empty box)
        global_popup_default = self._raw_config.get('auto_close_sec') or 20

        hdr = tk.Frame(f, bg=BG)
        hdr.pack(fill='x', padx=4, pady=(2, 0))
        tk.Label(hdr, text="", bg=BG, width=2).pack(side='left', padx=(8, 0))
        tk.Label(hdr, text="Reminder", font=('Segoe UI', 9, 'bold'),
                 fg=FG_DIM, bg=BG, width=22, anchor='w').pack(side='left')
        tk.Label(hdr, text="Every", font=('Segoe UI', 9, 'bold'),
                 fg=FG_DIM, bg=BG, width=7, anchor='center').pack(side='left', padx=(2, 0))
        tk.Label(hdr, text="Notification", font=('Segoe UI', 9, 'bold'),
                 fg=FG_DIM, bg=BG, width=11, anchor='center').pack(side='left', padx=(4, 0))
        tk.Label(hdr, text="Activity", font=('Segoe UI', 9, 'bold'),
                 fg=FG_DIM, bg=BG, width=7, anchor='center').pack(side='left', padx=(4, 0))
        # Subline of units, dim
        sub = tk.Frame(f, bg=BG)
        sub.pack(fill='x', padx=4)
        tk.Label(sub, text="", bg=BG, width=2).pack(side='left', padx=(8, 0))
        tk.Label(sub, text="", bg=BG, width=22, anchor='w').pack(side='left')
        tk.Label(sub, text="min", font=('Segoe UI', 8),
                 fg=FG_HINT, bg=BG, width=7, anchor='center').pack(side='left', padx=(2, 0))
        tk.Label(sub, text="sec visible", font=('Segoe UI', 8),
                 fg=FG_HINT, bg=BG, width=10, anchor='center').pack(side='left', padx=(0, 0))
        tk.Label(sub, text="sec", font=('Segoe UI', 8),
                 fg=FG_HINT, bg=BG, width=7, anchor='center').pack(side='left', padx=(0, 0))

        for rtype, label in REMINDER_LABELS.items():
            user_rcfg = reminders.get(rtype) or {}
            default_rcfg = default_reminders.get(rtype, {})
            row_data = {**default_rcfg, **user_rcfg}

            row = tk.Frame(f, bg=BG_CARD)
            row.pack(fill='x', pady=1, padx=4)

            enabled_var = tk.BooleanVar(value=row_data.get('enabled', True))
            tk.Checkbutton(row, variable=enabled_var, bg=BG_CARD,
                           activebackground=BG_CARD, selectcolor=BG_CARD,
                           fg=FG, activeforeground=FG).pack(side='left', padx=(8, 0))
            tk.Label(row, text=label, font=('Segoe UI', 10),
                     fg=FG, bg=BG_CARD, width=22, anchor='w').pack(side='left', padx=(0, 4))

            interval_var = tk.StringVar(
                value=_coerce_int_str(row_data.get('interval_min'), default="30"))
            interval_entry = tk.Entry(row, textvariable=interval_var, width=6,
                                      font=('Segoe UI', 10), bg=ENTRY_BG, fg=ENTRY_FG,
                                      insertbackground=FG, relief='flat',
                                      justify='center')
            interval_entry.pack(side='left', padx=(2, 0))

            # Popup-visible: show the EFFECTIVE value (per-reminder override
            # if set, else the global default) so users see what's in effect.
            ps_value = row_data.get('popup_stay_sec')
            ps_initial = (str(ps_value) if isinstance(ps_value, int) and ps_value > 0
                          else str(global_popup_default))
            popup_stay_var = tk.StringVar(value=ps_initial)
            popup_stay_entry = tk.Entry(row, textvariable=popup_stay_var, width=9,
                                        font=('Segoe UI', 10), bg=ENTRY_BG, fg=ENTRY_FG,
                                        insertbackground=FG, relief='flat',
                                        justify='center')
            popup_stay_entry.pack(side='left', padx=(4, 0))

            activity_var = tk.StringVar(
                value=_coerce_int_str(row_data.get('duration_sec')))
            activity_entry = tk.Entry(row, textvariable=activity_var, width=6,
                                      font=('Segoe UI', 10), bg=ENTRY_BG, fg=ENTRY_FG,
                                      insertbackground=FG, relief='flat',
                                      justify='center')
            activity_entry.pack(side='left', padx=(4, 8))

            self._reminder_vars[rtype] = {
                'enabled': enabled_var,
                'interval_min': interval_var,
                'popup_stay_sec': popup_stay_var,
                'duration_sec': activity_var,
                'interval_widget': interval_entry,
                'popup_stay_widget': popup_stay_entry,
                'activity_widget': activity_entry,
            }

        # --- Active Days ---
        self._section_label(f, "Active Days",
                            "Reminders only fire on the days you tick.")
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

        # --- Quiet Hours (single 24-hour timeline with a draggable block;
        #     the section title and live status are inline in the row built
        #     by _build_quiet_timeline below) ---
        # Migration: prefer quiet_ranges, fall back to legacy quiet_hours dict
        quiet_ranges = self._raw_config.get('quiet_ranges')
        if not quiet_ranges:
            legacy = self._raw_config.get('quiet_hours')
            if isinstance(legacy, dict):
                quiet_ranges = [legacy]
        if not quiet_ranges:
            quiet_ranges = [{"start": "22:00", "end": "07:00"}]
        first_range = quiet_ranges[0]

        start_h, start_m = _split_hhmm(first_range.get('start', '22:00'))
        end_h, end_m = _split_hhmm(first_range.get('end', '07:00'))

        # State held in two minute-of-day variables (0..1440)
        self._qs_min = start_h * 60 + start_m
        self._qe_min = end_h * 60 + end_m

        self._build_quiet_timeline(f)

        # --- Notification options (compact: just the monitor pick — each
        # reminder row already shows its own visible-time value) ---
        self._section_label(f, "Notification", None)
        gen_frame = tk.Frame(f, bg=BG)
        gen_frame.pack(fill='x', padx=8, pady=(0, 4))

        # Hidden global default — kept so old configs round-trip cleanly,
        # but no longer exposed because each reminder shows its own number.
        self._auto_close_var = tk.StringVar(
            value=_coerce_int_str(self._raw_config.get('auto_close_sec'), default="20"))
        self._auto_close_entry = None  # no widget — _save reads from var directly

        row2 = tk.Frame(gen_frame, bg=BG)
        row2.pack(fill='x', pady=2)
        tk.Label(row2, text="🖥  Show on", font=('Segoe UI', 10),
                 fg=FG, bg=BG).pack(side='left')
        self._monitor_var = tk.StringVar(
            value=self._raw_config.get('popup_monitor', 'primary'))
        for label_txt, val in MONITOR_OPTIONS:
            tk.Radiobutton(row2, text=label_txt, variable=self._monitor_var,
                           value=val, bg=BG, activebackground=BG,
                           selectcolor=BG_CARD, fg=FG, activeforeground=FG,
                           font=('Segoe UI', 10)).pack(side='left', padx=6)

        # Config file path hint (small footer)
        tk.Label(f, text=f"📁  {self.config_path}", font=('Segoe UI', 8),
                 fg=FG_HINT, bg=BG, wraplength=580).pack(pady=(8, 2), padx=8, anchor='w')

    def _section_label(self, parent, title: str, hint: Optional[str]):
        # Plain text header in accent color — no emoji (avoids OS color conflicts)
        tk.Label(parent, text=title, font=('Segoe UI', 12, 'bold'),
                 fg=ACCENT, bg=BG).pack(pady=(8, 2), anchor='w', padx=12)
        if hint:
            tk.Label(parent, text=hint, font=('Segoe UI', 9),
                     fg=FG_DIM, bg=BG).pack(pady=(0, 4), anchor='w', padx=12)

    # ── Quiet hours timeline ─────────────────────────────────

    _TL_HEIGHT = 70
    _TL_PADX = 16     # horizontal padding inside canvas
    _TL_BAR_Y = 22
    _TL_BAR_H = 26
    _TL_EDGE_GRAB = 8  # px from edge counts as edge-resize zone

    def _build_quiet_timeline(self, parent):
        # Inline title row: "Quiet Hours" on the left, live status on the right
        title_row = tk.Frame(parent, bg=BG)
        title_row.pack(fill='x', padx=12, pady=(8, 2))
        tk.Label(title_row, text="Quiet Hours", font=('Segoe UI', 12, 'bold'),
                 fg=ACCENT, bg=BG).pack(side='left')
        self._quiet_status = tk.Label(title_row, text="",
                                      font=('Segoe UI', 10, 'bold'),
                                      fg=MAUVE, bg=BG)
        self._quiet_status.pack(side='right')

        wrap = tk.Frame(parent, bg=BG)
        wrap.pack(fill='x', padx=12, pady=(2, 4))

        self._tl_canvas = tk.Canvas(wrap, height=self._TL_HEIGHT, bg=BG,
                                    highlightthickness=0)
        self._tl_canvas.pack(fill='x')
        self._tl_canvas.bind('<Configure>', lambda e: self._tl_redraw())

        # Status / readout below the bar
        readout = tk.Frame(parent, bg=BG)
        readout.pack(fill='x', padx=12, pady=(0, 4))
        self._quiet_status = tk.Label(readout, text="",
                                      font=('Segoe UI', 11, 'bold'),
                                      fg=ACCENT, bg=BG)
        self._quiet_status.pack(side='left')

        # Drag state: 'block' (move whole), 'start' (resize left), 'end' (resize right)
        self._tl_drag_mode: Optional[str] = None
        self._tl_drag_anchor_min = 0  # for 'block' drag: original quiet_start at press
        self._tl_drag_press_min = 0   # for 'block' drag: where on the timeline the press landed

        c = self._tl_canvas
        c.bind('<Motion>', self._tl_on_motion)
        c.bind('<Button-1>', self._tl_on_press)
        c.bind('<B1-Motion>', self._tl_on_drag)
        c.bind('<ButtonRelease-1>', self._tl_on_release)

        self._tl_redraw()

    def _tl_min_to_x(self, mins: int) -> float:
        c = self._tl_canvas
        w = c.winfo_width() or 400
        usable = max(1, w - 2 * self._TL_PADX)
        return self._TL_PADX + (mins / 1440.0) * usable

    def _tl_x_to_min(self, x: float, snap: int = 15) -> int:
        c = self._tl_canvas
        w = c.winfo_width() or 400
        usable = max(1, w - 2 * self._TL_PADX)
        rel = (x - self._TL_PADX) / usable
        rel = max(0.0, min(1.0, rel))
        mins = int(round(rel * 1440))
        return (mins // snap) * snap  # snap to 15-min increments

    def _tl_redraw(self):
        c = self._tl_canvas
        c.delete('all')
        w = c.winfo_width() or 400
        bar_top = self._TL_BAR_Y - self._TL_BAR_H // 2
        bar_bot = self._TL_BAR_Y + self._TL_BAR_H // 2
        left_x = self._TL_PADX
        right_x = w - self._TL_PADX

        s = self._qs_min
        e = self._qe_min
        sx = self._tl_min_to_x(s)
        ex = self._tl_min_to_x(e)

        # Background bar = active hours (green = "go, reminders firing")
        c.create_rectangle(left_x, bar_top, right_x, bar_bot,
                           fill=GREEN_DIM, outline=FG_HINT, width=1)

        # Quiet block = mauve/purple (night/sleep) — distinct from green active
        block_color = MAUVE
        if s == e:
            pass  # no block
        elif s < e:
            c.create_rectangle(sx, bar_top + 1, ex, bar_bot - 1,
                               fill=block_color, outline='', tags='block')
        else:
            c.create_rectangle(sx, bar_top + 1, right_x, bar_bot - 1,
                               fill=block_color, outline='', tags='block')
            c.create_rectangle(left_x, bar_top + 1, ex, bar_bot - 1,
                               fill=block_color, outline='', tags='block')

        # Hour tick marks + labels (every 3 hours)
        for hr in range(0, 25, 3):
            x = self._tl_min_to_x(hr * 60)
            c.create_line(x, bar_bot, x, bar_bot + 4, fill=FG_HINT, width=1)
            c.create_text(x, bar_bot + 12, text=f"{hr:02d}",
                          fill=FG_DIM, font=('Segoe UI', 8))

        # Edge handle indicators (small darker bars on each side of the block)
        if s != e:
            handle_color = '#1e1e2e'
            c.create_rectangle(sx, bar_top, sx + 3, bar_bot,
                               fill=handle_color, outline='')
            c.create_rectangle(ex - 3, bar_top, ex, bar_bot,
                               fill=handle_color, outline='')

        # Time labels above each handle
        if s != e:
            c.create_text(sx, bar_top - 6, text=f"{s // 60:02d}:{s % 60:02d}",
                          fill=FG, font=('Segoe UI', 9, 'bold'), anchor='s')
            c.create_text(ex, bar_top - 6, text=f"{e // 60:02d}:{e % 60:02d}",
                          fill=FG, font=('Segoe UI', 9, 'bold'), anchor='s')

        # Update readout
        self._tl_update_status()

    def _tl_update_status(self):
        s = self._qs_min
        e = self._qe_min
        if s == e:
            self._quiet_status.configure(text="No quiet hours", fg=FG_DIM)
        elif s > e:
            span = (1440 - s) + e
            self._quiet_status.configure(
                text=f"{s//60:02d}:{s%60:02d} → {e//60:02d}:{e%60:02d}  ·  "
                     f"overnight, {span//60}h{span%60:02d}m",
                fg=MAUVE)
        else:
            span = e - s
            self._quiet_status.configure(
                text=f"{s//60:02d}:{s%60:02d} → {e//60:02d}:{e%60:02d}  ·  "
                     f"{span//60}h{span%60:02d}m",
                fg=MAUVE)

    def _tl_hit_test(self, x: float) -> str:
        """Return 'start', 'end', 'block', or 'outside' based on cursor x."""
        s = self._qs_min
        e = self._qe_min
        if s == e:
            return 'outside'
        sx = self._tl_min_to_x(s)
        ex = self._tl_min_to_x(e)
        # Edge zones first
        if abs(x - sx) <= self._TL_EDGE_GRAB:
            return 'start'
        if abs(x - ex) <= self._TL_EDGE_GRAB:
            return 'end'
        # Inside block (handle wraparound)
        if s < e:
            if sx < x < ex:
                return 'block'
        else:
            c = self._tl_canvas
            w = c.winfo_width() or 400
            if x > sx or x < ex:
                return 'block'
        return 'outside'

    def _tl_on_motion(self, event):
        zone = self._tl_hit_test(event.x)
        cursors = {'start': 'sb_h_double_arrow', 'end': 'sb_h_double_arrow',
                   'block': 'fleur', 'outside': 'arrow'}
        self._tl_canvas.configure(cursor=cursors.get(zone, 'arrow'))

    def _tl_on_press(self, event):
        zone = self._tl_hit_test(event.x)
        if zone == 'outside':
            # Click on empty bar → move nearest edge to clicked spot
            mins = self._tl_x_to_min(event.x)
            ds = abs(mins - self._qs_min)
            de = abs(mins - self._qe_min)
            zone = 'start' if ds <= de else 'end'
            if zone == 'start':
                self._qs_min = mins
            else:
                self._qe_min = mins
            self._tl_redraw()
        self._tl_drag_mode = zone
        if zone == 'block':
            self._tl_drag_anchor_min = self._qs_min
            self._tl_drag_press_min = self._tl_x_to_min(event.x)

    def _tl_on_drag(self, event):
        if not self._tl_drag_mode:
            return
        mins = self._tl_x_to_min(event.x)
        if self._tl_drag_mode == 'start':
            self._qs_min = mins
        elif self._tl_drag_mode == 'end':
            self._qe_min = mins
        elif self._tl_drag_mode == 'block':
            # Preserve block duration; shift start by drag delta
            duration = (self._qe_min - self._qs_min) % 1440
            delta = mins - self._tl_drag_press_min
            new_start = (self._tl_drag_anchor_min + delta) % 1440
            self._qs_min = new_start
            self._qe_min = (new_start + duration) % 1440
        self._tl_redraw()

    def _tl_on_release(self, event):
        self._tl_drag_mode = None

    def _flash_field(self, widget):
        try:
            widget.configure(bg=ERR_BG)
            self.top.after(1500, lambda: widget.configure(bg=ENTRY_BG))
        except Exception:
            pass

    # ── Save (read-modify-write) ─────────────────────────────

    def _reset_to_defaults(self):
        """Overwrite config with bundled defaults and rebuild the dialog."""
        if not messagebox.askyesno(
                "Reset Sehat Settings",
                "Replace your current Sehat settings with the bundled defaults?\n\n"
                "This will reset reminders, schedule, quiet hours and notification "
                "options. The change is saved immediately.",
                parent=self.top):
            return
        try:
            defaults_text = DEFAULT_CONFIG_PATH.read_text(encoding='utf-8')
            tmp = self.config_path.with_suffix('.tmp')
            tmp.write_text(defaults_text, encoding='utf-8')
            tmp.replace(self.config_path)
        except Exception as e:
            messagebox.showerror("Reset failed", f"Could not write defaults:\n{e}",
                                 parent=self.top)
            return
        if self.on_save:
            self.on_save()
        # Rebuild from disk so the UI reflects the reset values
        self._raw_config = self._load_raw()
        self._original_reminders = set(self._raw_config.get('reminders', {}).keys())
        for child in self._inner.winfo_children():
            child.destroy()
        self._build_topbar()
        self._build_body()

    def _save(self):
        errors = []  # list of (message, optional_widget_to_flash)

        for rtype, vars_ in self._reminder_vars.items():
            label = REMINDER_LABELS.get(rtype, rtype)
            interval_str = vars_['interval_min'].get().strip()
            try:
                ival = int(interval_str)
                if ival < 1:
                    errors.append((f"{label}: 'every' must be ≥ 1 minute",
                                   vars_['interval_widget']))
            except ValueError:
                errors.append((f"{label}: 'every' must be a number (got '{interval_str}')",
                               vars_['interval_widget']))

            ps_str = vars_['popup_stay_sec'].get().strip()
            if ps_str != "":
                try:
                    psv = int(ps_str)
                    if psv < 1:
                        errors.append((f"{label}: popup visible must be ≥ 1 second (or blank)",
                                       vars_['popup_stay_widget']))
                except ValueError:
                    errors.append(
                        (f"{label}: popup visible must be a number or blank (got '{ps_str}')",
                         vars_['popup_stay_widget']))

            ad_str = vars_['duration_sec'].get().strip()
            if ad_str != "":
                try:
                    adv = int(ad_str)
                    if adv < 0:
                        errors.append((f"{label}: activity duration must be ≥ 0 (or blank)",
                                       vars_['activity_widget']))
                except ValueError:
                    errors.append(
                        (f"{label}: activity duration must be a number or blank (got '{ad_str}')",
                         vars_['activity_widget']))

        # Validate quiet hours — values come from timeline (0..1439, snapped to 15)
        # so they're always valid; just format them.
        qs = f"{self._qs_min // 60:02d}:{self._qs_min % 60:02d}"
        qe = f"{self._qe_min // 60:02d}:{self._qe_min % 60:02d}"

        # Auto-close global default: no widget exposed, just round-trip from var
        ac_str = self._auto_close_var.get().strip()
        try:
            ac_val = int(ac_str)
            if ac_val < 0:
                errors.append(("Default popup visible time: must be ≥ 0", None))
        except ValueError:
            errors.append((f"Default popup visible time: must be a number (got '{ac_str}')",
                           None))

        if errors:
            for _, widget in errors:
                if widget is not None:
                    self._flash_field(widget)
            messagebox.showerror(
                "Invalid Settings",
                "\n".join(f"• {msg}" for msg, _ in errors),
                parent=self.top)
            return

        # Read-modify-write
        cfg = self._raw_config.copy()
        reminders = dict(cfg.get('reminders', {}))
        default_reminders = self._defaults.get('reminders', {})

        for rtype, vars_ in self._reminder_vars.items():
            enabled = vars_['enabled'].get()
            existed = rtype in self._original_reminders
            if not existed and not enabled:
                continue
            entry = (dict(reminders[rtype]) if existed
                     else dict(default_reminders.get(rtype, {})))
            entry['enabled'] = enabled
            entry['interval_min'] = int(vars_['interval_min'].get().strip())
            ps_str = vars_['popup_stay_sec'].get().strip()
            entry['popup_stay_sec'] = int(ps_str) if ps_str else None
            ad_str = vars_['duration_sec'].get().strip()
            entry['duration_sec'] = int(ad_str) if ad_str else None
            # Note: jitter_min, align_to_clock, active_hours are preserved
            # from the source dict — never modified by this UI.
            reminders[rtype] = entry
        cfg['reminders'] = reminders

        cfg['active_days'] = [d for d in ALL_DAYS if self._day_vars[d].get()]

        # qs/qe were built above during validation
        cfg['quiet_ranges'] = [{"start": qs, "end": qe}]
        cfg['quiet_hours'] = {"start": qs, "end": qe}  # legacy mirror

        cfg['auto_close_sec'] = int(self._auto_close_var.get().strip())
        cfg['popup_monitor'] = self._monitor_var.get()

        try:
            SehatConfig(**cfg)
        except Exception as e:
            messagebox.showerror("Config Validation Error", str(e), parent=self.top)
            return

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
