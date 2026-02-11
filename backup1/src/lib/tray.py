"""System tray calendar using pystray + Tk popup.

Features:
- System tray icon via `pystray`.
- Popup calendar implemented with `tkinter` that is shown/hidden on:
  - Hover near the bottom-right corner (Windows heuristic polling).
  - Menu / Show Calendar toggle.
- Saturday: blue, Sunday & public holidays: red.

Notes:
- Hover detection is a heuristic (checks cursor near bottom-right). Windows
  doesn't provide a simple cross-library hover callback for tray icons, so
  this approach is pragmatic for most single-monitor default-taskbar setups.
"""

import threading
import calendar
import datetime
import time
import ctypes
from typing import Optional, Dict
import tempfile
import os

import tkinter as tk
from tkinter import font

from PIL import Image, ImageDraw
try:
    import win32api
    import win32con
    import win32gui
    import win32gui_struct
    HAS_PYWIN32 = True
except Exception:
    HAS_PYWIN32 = False

import pystray

from .holidays_provider import HolidaysProvider


def _create_icon_image(size=64, bg_color=(255, 255, 255)) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = size // 8
    draw.rectangle([margin, margin, size - margin, size - margin], fill=bg_color)
    return img


class CalendarPopup:
    def __init__(self, holidays: Dict[datetime.date, str]):
        self.holidays = holidays
        self.root = tk.Tk()
        self.root.withdraw()
        # Keep root hidden; we use a Toplevel for the popup
        self.popup = tk.Toplevel(self.root)
        self.popup.withdraw()
        self.popup.overrideredirect(True)
        self.popup.attributes("-topmost", True)
        self.frame = tk.Frame(self.popup, bd=1, relief=tk.SOLID, bg="#ffffff")
        self.frame.pack(fill=tk.BOTH, expand=True)
        self.current_year = None
        self.current_month = None
        self.day_labels = []
        self._build_base_styles()

    def _build_base_styles(self):
        self.font_small = font.Font(family="Segoe UI", size=10)
        self.font_day = font.Font(family="Segoe UI", size=10, weight="normal")

    def _clear(self):
        for child in self.frame.winfo_children():
            child.destroy()
        self.day_labels = []

    def show_month(self, year: int, month: int, x: int = None, y: int = None):
        if year == self.current_year and month == self.current_month:
            # already built; just show
            if x is not None and y is not None:
                self.popup.geometry(f"+{x}+{y}")
            self.popup.deiconify()
            return

        self.current_year = year
        self.current_month = month
        self._clear()

        header = tk.Label(self.frame, text=f"{year} - {month}", font=self.font_small, bg="#ffffff")
        header.grid(row=0, column=0, columnspan=7, padx=6, pady=(6, 2))

        # Weekday headers (Sunday..Saturday)
        for i, wd in enumerate(["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]):
            lbl = tk.Label(self.frame, text=wd, font=self.font_small, bg="#f0f0f0", width=4)
            lbl.grid(row=1, column=i, padx=1, pady=1)

        cal = calendar.Calendar(calendar.SUNDAY)
        month_weeks = cal.monthdayscalendar(year, month)
        today = datetime.date.today()

        for r, week in enumerate(month_weeks, start=2):
            for c, day in enumerate(week):
                if day == 0:
                    lbl = tk.Label(self.frame, text="", width=4, bg="#ffffff")
                else:
                    d = datetime.date(year, month, day)
                    fg = "#000000"
                    # Sunday index 0 (when using Calendar(calendar.SUNDAY))
                    if c == 0:
                        fg = "#c00000"  # red
                    elif c == 6:
                        fg = "#0060c0"  # blue
                    if d in self.holidays:
                        fg = "#c00000"
                    # highlight today's date with a gray background
                    bg = "#e8e8e8" if d == today else "#ffffff"
                    lbl = tk.Label(self.frame, text=str(day), font=self.font_day, fg=fg, width=4, bg=bg)
                lbl.grid(row=r, column=c, padx=1, pady=1)
                self.day_labels.append(lbl)

        # small padding
        self.frame.update_idletasks()
        if x is not None and y is not None:
            self.popup.geometry(f"+{x}+{y}")
        self.popup.deiconify()

    def hide(self):
        self.popup.withdraw()

    def destroy(self):
        try:
            self.popup.destroy()
            self.root.quit()
        except Exception:
            pass


class TrayApp:
    def __init__(self, years=None, hover_distance=220, poll_interval=0.12):
        self.years = years or [datetime.datetime.now().year]
        self.holidays_provider = HolidaysProvider(years=self.years)
        self.icon: Optional[pystray.Icon] = None
        self.popup: Optional[CalendarPopup] = None
        self._running = False
        self.hover_distance = hover_distance
        self.poll_interval = poll_interval
        self._hover_thread: Optional[threading.Thread] = None
        self._tk_thread: Optional[threading.Thread] = None

    def _quit(self, icon, item):
        self.stop()

    def _toggle_popup(self, icon=None, item=None):
        if not self.popup:
            return
        # Toggle: if visible -> hide, else show near bottom-right
        try:
            if self.popup.popup.state() == 'normal':
                self.popup.hide()
            else:
                sx = ctypes.windll.user32.GetSystemMetrics(0)
                sy = ctypes.windll.user32.GetSystemMetrics(1)
                # position above taskbar/footer
                x = max(10, sx - 300)
                y = max(10, sy - 220)
                self.popup.show_month(self.popup.current_year or datetime.datetime.now().year,
                                      self.popup.current_month or datetime.datetime.now().month,
                                      x, y)
        except Exception:
            # fallback: just show for current month
            now = datetime.datetime.now()
            sx = ctypes.windll.user32.GetSystemMetrics(0)
            sy = ctypes.windll.user32.GetSystemMetrics(1)
            x = max(10, sx - 300)
            y = max(10, sy - 220)
            self.popup.show_month(now.year, now.month, x, y)

    def start(self):
        # Prepare holidays
        holidays = self.holidays_provider.get_holidays()

        # Create the tkinter popup here (do NOT start its mainloop here).
        # The Tk mainloop must run on the main thread on Windows; the caller
        # (e.g. `src.main`) should call `app.popup.root.mainloop()` after
        # `app.start()` so the popup becomes responsive.
        self.popup = CalendarPopup(holidays)
        now = datetime.datetime.now()
        self.popup.show_month(now.year, now.month, sx := ctypes.windll.user32.GetSystemMetrics(0) - 300,
                              sy := ctypes.windll.user32.GetSystemMetrics(1) - 220)

        # If pywin32 is available, create a native tray icon and catch exact hover events.
        if HAS_PYWIN32:
            # Create temporary .ico file from PIL image
            ico_path = None
            try:
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".ico")
                ico_path = tmp.name
                tmp.close()
                _create_icon_image(64).save(ico_path, format="ICO")

                # Window class and message loop
                message_map = {}

                WM_TRAY = win32con.WM_USER + 20

                last_move = {"t": 0.0}
                hide_timeout = 0.6

                def _wndproc(hwnd, msg, wparam, lparam):
                    if msg == WM_TRAY:
                        if lparam == win32con.WM_MOUSEMOVE:
                            # show popup and update last-move timestamp
                            try:
                                now = datetime.datetime.now()
                                sx = win32api.GetSystemMetrics(0)
                                sy = win32api.GetSystemMetrics(1)
                                if self.popup:
                                    self.popup.show_month(now.year, now.month, max(10, sx - 300), max(10, sy - 220))
                                last_move["t"] = time.time()
                            except Exception:
                                pass
                        elif lparam in (win32con.WM_LBUTTONDOWN, win32con.WM_RBUTTONDOWN):
                            # toggle on click
                            try:
                                self._toggle_popup()
                            except Exception:
                                pass
                    return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

                # Register window class
                wc = win32gui.WNDCLASS()
                hinst = wc.hInstance = win32api.GetModuleHandle(None)
                wc.lpszClassName = "KrCalendarTray"
                wc.lpfnWndProc = _wndproc
                class_atom = win32gui.RegisterClass(wc)
                hwnd = win32gui.CreateWindow(wc.lpszClassName, "KrCalendarHiddenWindow", 0, 0, 0, 0, 0, 0, 0, hinst, None)

                # Load icon
                hicon = win32gui.LoadImage(hinst, ico_path, win32con.IMAGE_ICON, 0, 0, win32con.LR_LOADFROMFILE)

                nid = (hwnd, 1, win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP, WM_TRAY, hicon, "krCalendar")
                win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, nid)

                # run message pump in a thread
                def pump():
                    while True:
                        msg = win32gui.GetMessage(None, 0, 0)
                        if not msg:
                            break
                        win32gui.TranslateMessage(msg)
                        win32gui.DispatchMessage(msg)
                t = threading.Thread(target=pump, daemon=True)
                t.start()

                # start a watcher to hide popup after no mousemoves for hide_timeout
                def native_hide_watcher():
                    while True:
                        try:
                            if self.popup and (time.time() - last_move.get("t", 0)) > hide_timeout:
                                try:
                                    self.popup.hide()
                                except Exception:
                                    pass
                        except Exception:
                            pass
                        time.sleep(0.1)

                w = threading.Thread(target=native_hide_watcher, daemon=True)
                w.start()
            except Exception:
                # fallback to pystray heuristic if anything fails
                pass
            finally:
                if ico_path and os.path.exists(ico_path):
                    try:
                        os.unlink(ico_path)
                    except Exception:
                        pass
        else:
            # Start hover monitor (Windows heuristic)
            def hover_monitor():
                self._running = True
                was_visible = True
                while self._running:
                    # get cursor
                    pt = ctypes.wintypes.POINT()
                    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
                    x, y = pt.x, pt.y
                    sx = ctypes.windll.user32.GetSystemMetrics(0)
                    sy = ctypes.windll.user32.GetSystemMetrics(1)
                    # if cursor is within hover_distance of bottom-right, show
                    near = (sx - x) <= self.hover_distance and (sy - y) <= self.hover_distance
                    try:
                        if near and self.popup:
                            # show at anchored position
                            self.popup.show_month(self.popup.current_year or datetime.datetime.now().year,
                                                  self.popup.current_month or datetime.datetime.now().month,
                                                  max(10, sx - 300), max(10, sy - 220))
                            was_visible = True
                        else:
                            if self.popup:
                                self.popup.hide()
                            was_visible = False
                    except Exception:
                        pass
                    time.sleep(self.poll_interval)

            self._hover_thread = threading.Thread(target=hover_monitor, daemon=True)
            self._hover_thread.start()

        # Start tray icon
        image = _create_icon_image()
        menu = pystray.Menu(
            pystray.MenuItem('Show Calendar', self._toggle_popup),
            pystray.MenuItem('Quit', self._quit),
        )
        self.icon = pystray.Icon('krcalendar', image, "krCalendar", menu)
        thread = threading.Thread(target=self.icon.run, daemon=True)
        thread.start()

    def stop(self):
        self._running = False
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass
        if self.popup:
            try:
                self.popup.destroy()
            except Exception:
                pass
