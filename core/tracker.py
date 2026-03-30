"""
Focus Engine Pro — Activity Tracker
Polls the foreground window every 2 seconds, classifies activity,
logs to database, and manages token earn/deduct logic.
Tracks Spotify via window title (no pycaw needed).
"""

import os
import re
import sys
import time
import ctypes
import ctypes.wintypes
import threading
import datetime
import psutil
from core import database as db


# ─── Windows API declarations ─────────────────────────────────────────────

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

GetForegroundWindow = user32.GetForegroundWindow
GetWindowTextW = user32.GetWindowTextW
GetWindowTextLengthW = user32.GetWindowTextLengthW
GetWindowThreadProcessId = user32.GetWindowThreadProcessId
IsZoomed = user32.IsZoomed  # Returns non-zero if window is maximized
IsIconic = user32.IsIconic   # Returns non-zero if window is minimized


def get_foreground_info() -> dict:
    """Get info about the currently focused window."""
    hwnd = GetForegroundWindow()
    if not hwnd:
        return {"app": "Desktop", "title": "Windows Desktop", "pid": 0}

    # Get window title
    length = GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    GetWindowTextW(hwnd, buf, length + 1)
    title = buf.value

    # Get PID
    pid = ctypes.wintypes.DWORD()
    GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

    # Get process name from PID
    app_name = "Unknown"
    try:
        proc = psutil.Process(pid.value)
        app_name = proc.name()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

    # Check if window is maximized (anti-cheat: study only counts when maximized)
    is_maximized = bool(IsZoomed(hwnd))

    return {"app": app_name, "title": title, "pid": pid.value, "is_maximized": is_maximized}


# ─── Activity Classification ──────────────────────────────────────────────

# Category keyword maps
STUDY_APPS = {
    "code.exe", "code - insiders.exe", "devenv.exe",
    "pycharm64.exe", "pycharm.exe", "idea64.exe", "idea.exe",
    "sublime_text.exe", "notepad++.exe", "atom.exe",
    "windowsterminal.exe", "powershell.exe", "cmd.exe",
    "cursor.exe", "windsurf.exe",
    "winword.exe", "excel.exe", "powerpnt.exe",
    "onenote.exe", "teams.exe",
    "acrobat.exe", "acrord32.exe",  # PDF readers
}

STUDY_TITLE_KEYWORDS = [
    "stack overflow", "stackoverflow", "github", "geeksforgeeks",
    "leetcode", "hackerrank", "docs.python", "docs.microsoft",
    "mdn web docs", "w3schools", "tutorialspoint", "coursera",
    "udemy", "khan academy", "edx", "codecademy",
    "jupyter", "notebook", "colab",
    ".py", ".js", ".html", ".css", ".java", ".cpp",
]

SOCIAL_MEDIA_KEYWORDS = [
    "instagram", "facebook", "twitter", "snapchat", "tiktok",
    "reddit", "whatsapp web", "telegram web", "pinterest",
    "tumblr", "linkedin",
]

ENTERTAINMENT_KEYWORDS = [
    "netflix", "disney+", "hotstar", "prime video", "hulu",
    "twitch", "crunchyroll", "youtube",  # YouTube classified here initially
    "hbo max", "peacock", "paramount+",
]

GAMING_KEYWORDS = [
    "steam", "epic games", "riot", "valorant", "fortnite",
    "gta", "minecraft", "roblox", "league of legends",
]

SPOTIFY_EXE = "spotify.exe"

# Whitelisted websites loaded from DB (used for browser title classification)
_whitelisted_websites = []
_whitelisted_yt_channels = []

def load_whitelists_from_db():
    """Load whitelisted websites and YouTube channels from settings."""
    global _whitelisted_websites, _whitelisted_yt_channels
    try:
        wl = db.get_setting("whitelisted_websites", "")
        if wl:
            _whitelisted_websites = [w.strip().lower() for w in wl.split(",") if w.strip()]
        ch = db.get_setting("whitelisted_channels", "")
        if ch:
            _whitelisted_yt_channels = [c.strip().lower() for c in ch.split(",") if c.strip()]
    except Exception:
        pass


def classify_activity(app_name: str, window_title: str, is_maximized: bool = True) -> str:
    """
    Classify window activity into categories.
    Study only counts when window is maximized (anti-split-screen cheat).
    Returns: 'study' | 'gaming' | 'social' | 'entertainment' | 'idle' | 'productivity' | 'other'
    """
    app_lower = app_name.lower()
    title_lower = window_title.lower()

    # Idle / Desktop
    if app_lower in ("explorer.exe",) and ("desktop" in title_lower or not window_title.strip()):
        return "idle"

    # Lockscreen / screensaver
    if app_lower in ("lockapp.exe", "logonui.exe"):
        return "idle"

    # No window
    if app_lower == "unknown" or not window_title.strip():
        return "idle"

    # Study apps (IDEs, editors) — still require maximized
    if app_lower in STUDY_APPS:
        return "study" if is_maximized else "productivity"

    # Browser — classify by page title
    if app_lower in ("chrome.exe", "msedge.exe", "firefox.exe", "brave.exe"):
        # Check whitelisted websites first
        for domain in _whitelisted_websites:
            if domain in title_lower:
                return "study" if is_maximized else "productivity"

        # Check YouTube with whitelisted channels
        if "youtube" in title_lower:
            # Check if a whitelisted channel name appears in the title
            for ch in _whitelisted_yt_channels:
                if ch in title_lower:
                    return "study" if is_maximized else "productivity"

        # Check study keywords
        for kw in STUDY_TITLE_KEYWORDS:
            if kw in title_lower:
                return "study" if is_maximized else "productivity"
        # Check social media
        for kw in SOCIAL_MEDIA_KEYWORDS:
            if kw in title_lower:
                return "social"
        # Check entertainment
        for kw in ENTERTAINMENT_KEYWORDS:
            if kw in title_lower:
                return "entertainment"
        # Check gaming
        for kw in GAMING_KEYWORDS:
            if kw in title_lower:
                return "gaming"
        # Default browser = productivity (research, etc.)
        return "productivity"

    # Spotify
    if app_lower == SPOTIFY_EXE:
        return "entertainment"

    # Productivity apps
    if app_lower in ("winword.exe", "excel.exe", "powerpnt.exe", "onenote.exe",
                     "outlook.exe", "teams.exe", "zoom.exe", "slack.exe"):
        return "productivity"

    # Check title for gaming
    for kw in GAMING_KEYWORDS:
        if kw in title_lower:
            return "gaming"

    return "other"


# ─── Spotify Title Parser ─────────────────────────────────────────────────

def parse_spotify_title(title: str) -> dict:
    """
    Spotify window title format: "Song Name - Artist Name" or "Spotify Free" / "Spotify Premium"
    """
    if not title or title.lower() in ("spotify", "spotify free", "spotify premium"):
        return {"playing": False, "track": "", "artist": ""}

    parts = title.split(" - ", 1)
    if len(parts) == 2:
        return {"playing": True, "track": parts[0].strip(), "artist": parts[1].strip()}
    return {"playing": True, "track": title, "artist": ""}


# ─── Activity Tracker Thread ──────────────────────────────────────────────

class ActivityTracker:
    """Polls foreground window every 2 seconds, accumulates and flushes to DB."""

    def __init__(self):
        self._running = False
        self._thread = None
        self._accumulated = {}  # (app, category) -> {seconds, last_title}
        self._spotify_log = []  # Track Spotify history (deduplicated)
        self._last_spotify_track = ""  # Last logged track for dedup
        self._spotify_listen_seconds = 0  # Accumulated listening seconds
        self._last_flush = time.time()
        self._study_accumulator = 0  # Seconds of study since last token earn
        self._gaming_accumulator = 0  # Seconds of gaming since last token deduct
        self._token_earn_rate = int(db.get_setting("token_earn_rate", "30"))
        self._token_deduct_rate = int(db.get_setting("token_deduct_rate", "15"))
        self.on_flush = None  # Callback after data flush (for server push)

    def start(self):
        """Start the tracker in a daemon thread."""
        load_whitelists_from_db()  # Load whitelisted websites/channels
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _run_loop(self):
        """Main tracking loop — runs every 2 seconds."""
        POLL_INTERVAL = 2
        FLUSH_INTERVAL = 30  # Write to DB every 30 seconds
        TOKEN_INTERVAL = 60  # Check tokens every minute

        last_token_check = time.time()

        while self._running:
            try:
                info = get_foreground_info()
                app = info["app"]
                title = info["title"]
                is_maximized = info.get("is_maximized", True)
                category = classify_activity(app, title, is_maximized)

                # Accumulate
                key = (app, category)
                if key not in self._accumulated:
                    self._accumulated[key] = {"seconds": 0, "last_title": title}
                self._accumulated[key]["seconds"] += POLL_INTERVAL
                self._accumulated[key]["last_title"] = title

                # Track Spotify (deduplicated)
                if app.lower() == SPOTIFY_EXE:
                    sp_info = parse_spotify_title(title)
                    if sp_info["playing"]:
                        track_key = f"{sp_info['track']} - {sp_info['artist']}"
                        if track_key != self._last_spotify_track:
                            # New track — finalize previous track's duration
                            if self._spotify_log and self._spotify_listen_seconds > 0:
                                self._spotify_log[-1]["duration"] = self._spotify_listen_seconds
                            # Add new entry
                            self._spotify_log.append({
                                "time": datetime.datetime.now().isoformat(),
                                "track": sp_info["track"],
                                "artist": sp_info["artist"],
                                "duration": 0,
                            })
                            self._last_spotify_track = track_key
                            self._spotify_listen_seconds = POLL_INTERVAL
                        else:
                            # Same track — accumulate listening time
                            self._spotify_listen_seconds += POLL_INTERVAL
                            if self._spotify_log:
                                self._spotify_log[-1]["duration"] = self._spotify_listen_seconds

                # Token accumulators
                if category == "study":
                    self._study_accumulator += POLL_INTERVAL
                elif category == "gaming":
                    self._gaming_accumulator += POLL_INTERVAL

                # Flush to database periodically
                now = time.time()
                if now - self._last_flush >= FLUSH_INTERVAL:
                    self._flush_to_db()
                    self._last_flush = now

                # Token calculation every minute
                if now - last_token_check >= TOKEN_INTERVAL:
                    self._process_tokens()
                    last_token_check = now

            except Exception as e:
                print(f"  [!] Tracker error: {e}")

            time.sleep(POLL_INTERVAL)

    def _flush_to_db(self):
        """Write accumulated data to SQLite."""
        try:
            for (app, category), data in self._accumulated.items():
                if data["seconds"] > 0:
                    db.log_screen_time(app, data["last_title"], category, data["seconds"])
            self._accumulated.clear()

            # Update daily summary
            today = datetime.date.today().isoformat()
            try:
                db.update_daily_summary(today)
            except Exception:
                pass

            # Notify the API server to push updated data to clients
            if self.on_flush:
                try:
                    self.on_flush()
                except Exception:
                    pass
        except Exception as e:
            print(f"  [!] Tracker flush error (will retry next cycle): {e}")

    def _process_tokens(self):
        """Earn tokens for study, deduct for gaming."""
        # Earn: 30 tokens per hour of study → 0.5 tokens per minute
        if self._study_accumulator >= 60:
            minutes = self._study_accumulator // 60
            tokens = int(minutes * (self._token_earn_rate / 60))
            if tokens > 0:
                db.earn_tokens(tokens, "study_time")
            self._study_accumulator = self._study_accumulator % 60

        # Deduct: 15 tokens per hour of gaming → 0.25 tokens per minute
        if self._gaming_accumulator >= 60:
            minutes = self._gaming_accumulator // 60
            tokens = int(minutes * (self._token_deduct_rate / 60))
            if tokens > 0:
                db.spend_tokens(tokens, "gaming_time")
            self._gaming_accumulator = self._gaming_accumulator % 60

    def get_current_activity(self) -> dict:
        """Return what's happening right now (for live dashboard feed)."""
        info = get_foreground_info()
        category = classify_activity(info["app"], info["title"])
        spotify = None
        if info["app"].lower() == SPOTIFY_EXE:
            spotify = parse_spotify_title(info["title"])
        return {
            "app": info["app"],
            "title": info["title"],
            "category": category,
            "spotify": spotify,
            "gaming_minutes": 0,
        }

    def get_spotify_history(self) -> list:
        """Return recent Spotify tracks."""
        return self._spotify_log[-50:]  # Last 50 tracks
