"""
Focus Engine Pro — Watchdog & Task Scheduler
Creates a Windows Task Scheduler entry on first run for auto-start at login.
Sets process priority to HIGH to resist Task Manager kills.
"""

import os
import sys
import ctypes
import subprocess
import psutil


def _base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


TASK_NAME = "FocusEnginePro"


class Watchdog:
    """Manages self-protection and scheduled task creation."""

    def __init__(self):
        self._is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0

    # ── Task Scheduler ────────────────────────────────────────────────────

    def is_task_scheduled(self) -> bool:
        """Check if our scheduled task already exists."""
        try:
            result = subprocess.run(
                ["schtasks", "/Query", "/TN", TASK_NAME],
                capture_output=True, text=True
            )
            return result.returncode == 0
        except Exception:
            return False

    def create_scheduled_task(self):
        """Create a Task Scheduler entry to auto-start at login with admin privileges."""
        if not self._is_admin:
            print("  [!] Need admin to create scheduled task. Skipping.")
            return False

        if self.is_task_scheduled():
            print("  [+] Scheduled task already exists.")
            return True

        # Determine the command to run
        if getattr(sys, 'frozen', False):
            # Running as .exe
            program = sys.executable
            args = ""
        else:
            # Running as .py script
            python_exe = sys.executable
            script = os.path.join(_base_dir(), "main.py")
            program = python_exe
            args = f'"{script}"'

        try:
            # Create task: run at logon with highest privileges
            cmd = [
                "schtasks", "/Create",
                "/TN", TASK_NAME,
                "/TR", f'"{program}" {args}'.strip(),
                "/SC", "ONLOGON",
                "/RL", "HIGHEST",
                "/F",  # Force overwrite
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                print(f"  [+] Scheduled task '{TASK_NAME}' created (runs at login)")
                return True
            else:
                print(f"  [!] Failed to create task: {result.stderr.strip()}")
                return False
        except Exception as e:
            print(f"  [!] Task Scheduler error: {e}")
            return False

    def remove_scheduled_task(self) -> bool:
        """Remove the scheduled task (called on uninstall/disable)."""
        if not self._is_admin:
            return False
        try:
            result = subprocess.run(
                ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                print(f"  [+] Scheduled task '{TASK_NAME}' removed")
            return result.returncode == 0
        except Exception:
            return False

    # ── Process Protection ────────────────────────────────────────────────

    def set_high_priority(self):
        """Set current process to HIGH priority to resist Task Manager kills."""
        try:
            proc = psutil.Process(os.getpid())
            proc.nice(psutil.HIGH_PRIORITY_CLASS)
            print("  [+] Process priority set to HIGH")
        except Exception as e:
            print(f"  [!] Could not set high priority: {e}")

    def protect_process(self):
        """Apply all protection mechanisms."""
        self.set_high_priority()
