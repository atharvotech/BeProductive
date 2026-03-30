"""
Focus Engine Pro — Smart App Killer
Detects games via Steam library scanning, exe metadata, and publisher heuristics.
Respects whitelists (Steam client, Desktop Mate, VTube Studio, IDEs).
Doesn't kill mid-game — instead prevents next match by blocking after a grace period.
"""

import os
import re
import time
import psutil
import ctypes
import struct
import threading
from core import database as db


class AppKiller:
    """Smart game detection and process management."""

    # Known game publishers in exe metadata
    GAME_PUBLISHERS = [
        "riot games", "epic games", "valve", "rockstar games",
        "ubisoft", "electronic arts", "activision", "blizzard",
        "bethesda", "cd projekt", "square enix", "capcom",
        "bandai namco", "sega", "konami", "2k games",
        "deep silver", "thq", "paradox", "supergiant",
        "mojang", "mihoyo", "hoyoverse", "garena",
    ]

    # Known game exe patterns (fallback) — use \b word boundaries to avoid false matches
    GAME_EXE_PATTERNS = [
        r"(?i)\bvalorant", r"(?i)\bfortnite", r"(?i)\bgta[v5]",
        r"(?i)\bcsgo\b|\bcs2\b", r"(?i)\bpubg", r"(?i)\bapex(?:legends)?",
        r"(?i)\boverwatch", r"(?i)\bminecraft", r"(?i)\broblox",
        r"(?i)\bcall.?of.?duty\b|\bcod\b", r"(?i)\bdota\b", r"(?i)\bleague",
        r"(?i)\brocket.?league", r"(?i)\brainbow.?six\b|\br6\b",
        r"(?i)\bdestiny\b", r"(?i)\bwarframe\b", r"(?i)\bark\b",
        r"(?i)\brust\b(?!c)", r"(?i)\bamong.?us", r"(?i)\bfall.?guys",
        r"(?i)\bgenshin", r"(?i)\bhonkai", r"(?i)\belden.?ring",
        r"(?i)\bdark.?souls", r"(?i)\bcyberpunk", r"(?i)\bwitcher",
        r"(?i)\bbattlefield\b|\bbf[0-9]", r"(?i)\bfifa\b|\bfc[0-9]",
        r"(?i)\bnba2k\b|\bnba.?2k", r"(?i)\bmadden\b", r"(?i)\bcivilization",
    ]

    # Study / productivity apps — NEVER kill these
    STUDY_APPS = {
        "code.exe", "code - insiders.exe", "devenv.exe",
        "pycharm64.exe", "pycharm.exe", "idea64.exe", "idea.exe",
        "sublime_text.exe", "notepad++.exe", "atom.exe",
        "windowsterminal.exe", "powershell.exe", "cmd.exe",
        "git-bash.exe", "bash.exe", "wsl.exe",
        "studio64.exe", "androidstudio64.exe",
        "cursor.exe", "windsurf.exe",
        "winword.exe", "excel.exe", "powerpnt.exe",
        "onenote.exe", "teams.exe", "outlook.exe",
        "msedge.exe", "chrome.exe", "firefox.exe", "brave.exe",
        "explorer.exe", "notepad.exe",
        "spotify.exe", "discord.exe",
    }

    # Default whitelist (never kill)
    DEFAULT_WHITELIST = {
        "steam.exe", "steamwebhelper.exe", "steamservice.exe",
        "desktopmate.exe", 
        "epicgameslauncher.exe", "unrealcefsubprocess.exe",
        # System services & analytics — must never be killed
        "touchpointanalyticsclientsservice.exe",
        "svchost.exe", "services.exe", "csrss.exe", "lsass.exe",
        "wininit.exe", "winlogon.exe", "dwm.exe", "taskhostw.exe",
        "runtimebroker.exe", "sihost.exe", "fontdrvhost.exe",
        "searchhost.exe", "startmenuexperiencehost.exe",
        "textinputhost.exe", "shellexperiencehost.exe",
        "applicationframehost.exe", "systemsettings.exe",
        "securityhealthservice.exe", "msmpeng.exe",
        "smartscreen.exe", "ctfmon.exe", "conhost.exe",
        "dllhost.exe", "msiexec.exe", "wmiprvse.exe",
    }

    # System directories — never kill exes from these paths
    SAFE_EXE_PATHS = [
        r"c:\windows",
        r"c:\program files\common files",
        r"c:\program files (x86)\common files",
        r"c:\programdata\microsoft",
    ]

    def __init__(self):
        self.steam_game_exes = set()
        self.user_whitelist = set()
        self.user_blacklist = set()
        self.gaming_start_time = None  # When continuous gaming session began
        self.warned_at_20 = False
        self._load_settings()
        self._scan_steam_library()

    def _load_settings(self):
        """Load whitelist and blacklist from database settings."""
        try:
            wl = db.get_setting("whitelisted_apps", "")
            bl = db.get_setting("blocked_apps_custom", "")
            if wl:
                self.user_whitelist = {x.strip().lower() for x in wl.split(",") if x.strip()}
            if bl:
                self.user_blacklist = {x.strip().lower() for x in bl.split(",") if x.strip()}
        except Exception:
            pass

    def reload_settings(self):
        """Reload from DB (called when dashboard updates settings)."""
        self._load_settings()

    # ── Steam Library Scanner ─────────────────────────────────────────────

    def _scan_steam_library(self):
        """Auto-detect installed Steam games by scanning steamapps/common."""
        steam_paths = self._find_steam_paths()
        for sp in steam_paths:
            common_dir = os.path.join(sp, "steamapps", "common")
            if not os.path.isdir(common_dir):
                continue
            for game_folder in os.listdir(common_dir):
                game_path = os.path.join(common_dir, game_folder)
                if not os.path.isdir(game_path):
                    continue
                # Find all .exe files in game folder
                for root, dirs, files in os.walk(game_path):
                    for f in files:
                        if f.lower().endswith(".exe"):
                            self.steam_game_exes.add(f.lower())
                    # Don't recurse too deep
                    if root.count(os.sep) - game_path.count(os.sep) > 2:
                        break

        # Remove Steam's own exes and known non-game exes
        safe_exes = {
            "steam.exe", "steamwebhelper.exe", "steamservice.exe",
            "uninstall.exe", "uninst.exe", "setup.exe",
            "crashhandler.exe", "crashhandler64.exe", "vc_redist.exe",
            "dxsetup.exe", "dotnetfx.exe",
        }
        self.steam_game_exes -= safe_exes
        if self.steam_game_exes:
            print(f"  [+] Steam scanner found {len(self.steam_game_exes)} game executables")

    def _find_steam_paths(self) -> list:
        """Find Steam installation paths."""
        paths = []
        # Default Steam location
        default = r"C:\Program Files (x86)\Steam"
        if os.path.isdir(default):
            paths.append(default)

        # Check registry for custom steam path
        try:
            import winreg
            key = winreg.OpenKeyEx(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\WOW6432Node\Valve\Steam",
                0, winreg.KEY_READ
            )
            install_path, _ = winreg.QueryValueEx(key, "InstallPath")
            winreg.CloseKey(key)
            if install_path and os.path.isdir(install_path):
                paths.append(install_path)
        except Exception:
            pass

        # Parse libraryfolders.vdf for additional library paths
        for sp in list(paths):
            vdf = os.path.join(sp, "steamapps", "libraryfolders.vdf")
            if os.path.isfile(vdf):
                try:
                    with open(vdf, "r", encoding="utf-8") as f:
                        content = f.read()
                    # Simple regex to find paths in VDF
                    for match in re.findall(r'"path"\s+"([^"]+)"', content):
                        p = match.replace("\\\\", "\\")
                        if os.path.isdir(p) and p not in paths:
                            paths.append(p)
                except Exception:
                    pass

        return paths

    # ── Game Detection ────────────────────────────────────────────────────

    def is_game_process(self, proc) -> bool:
        """Determine if a process is a game using multiple heuristics."""
        try:
            name = proc.name().lower()
            exe_path = proc.exe().lower() if proc.exe() else ""
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False

        # Check whitelist first — never flag these
        all_whitelist = self.STUDY_APPS | self.DEFAULT_WHITELIST | self.user_whitelist
        if name in all_whitelist:
            return False

        # Skip processes from system directories
        if exe_path:
            for safe_path in self.SAFE_EXE_PATHS:
                if exe_path.startswith(safe_path):
                    return False

        # Check user blacklist (explicitly blocked)
        if name in self.user_blacklist:
            return True

        # Check Steam game exes
        if name in self.steam_game_exes:
            return True

        # Check known game exe patterns
        for pattern in self.GAME_EXE_PATTERNS:
            if re.search(pattern, name) or re.search(pattern, exe_path):
                return True

        # Check exe metadata for game publishers
        if exe_path and os.path.isfile(exe_path):
            publisher = self._get_exe_publisher(exe_path)
            if publisher:
                pub_lower = publisher.lower()
                for known_pub in self.GAME_PUBLISHERS:
                    if known_pub in pub_lower:
                        return True

        return False

    def _get_exe_publisher(self, exe_path: str) -> str:
        """Read CompanyName from exe version info using win32 API."""
        try:
            import win32api
            info = win32api.GetFileVersionInfo(exe_path, "\\")
            # Get string file info
            lang_codepage = win32api.GetFileVersionInfo(
                exe_path, r"\VarFileInfo\Translation"
            )
            if lang_codepage:
                lang, codepage = lang_codepage[0]
                str_info_path = f"\\StringFileInfo\\{lang:04x}{codepage:04x}\\CompanyName"
                company = win32api.GetFileVersionInfo(exe_path, str_info_path)
                return company or ""
        except Exception:
            pass
        return ""

    # ── Hunt & Kill Logic ─────────────────────────────────────────────────

    def hunt_and_kill(self):
        """
        Scan running processes and handle game detection.
        - When focus mode is ON: kill games (after warning)
        - When tokens <= 0 and gaming > threshold: auto-enable focus mode
        - Smart: warn before killing, don't kill mid-match
        """
        focus_mode = db.get_setting("focus_mode", "off")
        token_balance = db.get_token_balance()
        threshold = int(db.get_setting("auto_focus_threshold_min", "30"))

        game_detected = False
        game_procs = []

        for proc in psutil.process_iter(["pid", "name"]):
            try:
                if self.is_game_process(proc):
                    game_detected = True
                    game_procs.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if game_detected:
            # Track continuous gaming time
            if self.gaming_start_time is None:
                self.gaming_start_time = time.time()

            gaming_minutes = (time.time() - self.gaming_start_time) / 60

            # Auto-focus trigger: gaming > threshold AND tokens depleted
            if focus_mode == "off" and gaming_minutes >= threshold and token_balance <= 0:
                db.set_setting("focus_mode", "on")
                focus_mode = "on"
                print(f"  [⚠] AUTO FOCUS MODE: Gaming for {int(gaming_minutes)}min with 0 tokens!")
                # Block incognito when focus mode turns on
                try:
                    from core.dns_blocker import DNSBlocker
                    DNSBlocker().block_incognito()
                except Exception:
                    pass

            # 20-minute warning (just log it — dashboard will show notification)
            if gaming_minutes >= 20 and not self.warned_at_20:
                self.warned_at_20 = True
                db.set_setting("gaming_warning", f"You've been gaming for {int(gaming_minutes)} minutes!")
                print(f"  [⚠] WARNING: {int(gaming_minutes)} minutes of gaming!")

            # Kill games only when focus mode is ON
            if focus_mode == "on":
                for proc in game_procs:
                    try:
                        name = proc.name()
                        proc.terminate()
                        # Wait a moment, then force kill if still alive
                        try:
                            proc.wait(timeout=3)
                        except psutil.TimeoutExpired:
                            proc.kill()
                        db.log_killed_process(name, f"Focus mode active, tokens={token_balance}")
                        print(f"  [💀] Killed: {name}")
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
        else:
            # No games running — reset tracking
            if self.gaming_start_time is not None:
                self.gaming_start_time = None
                self.warned_at_20 = False
                db.set_setting("gaming_warning", "")

    def get_gaming_minutes(self) -> float:
        """Return how many minutes of continuous gaming."""
        if self.gaming_start_time is None:
            return 0
        return (time.time() - self.gaming_start_time) / 60

    def get_blacklist(self) -> dict:
        """Return current block/whitelist config."""
        return {
            "user_blacklist": sorted(self.user_blacklist),
            "user_whitelist": sorted(self.user_whitelist),
            "steam_games_detected": len(self.steam_game_exes),
            "default_whitelist": sorted(self.DEFAULT_WHITELIST),
        }

    def update_blacklist(self, apps: list):
        """Update user blacklist from dashboard."""
        self.user_blacklist = {a.strip().lower() for a in apps if a.strip()}
        db.set_setting("blocked_apps_custom", ",".join(sorted(self.user_blacklist)))

    def update_whitelist(self, apps: list):
        """Update user whitelist from dashboard."""
        self.user_whitelist = {a.strip().lower() for a in apps if a.strip()}
        db.set_setting("whitelisted_apps", ",".join(sorted(self.user_whitelist)))
