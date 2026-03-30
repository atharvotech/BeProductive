"""
Focus Engine Pro — Admin Authentication & File Protection
Handles password hashing, security questions, forgot-password flow,
and exclusive file locking to prevent config tampering while running.
"""

import os
import sys
import json
import time
import bcrypt
import msvcrt
import hashlib
import datetime

# ---------------------------------------------------------------------------
# Path helpers (PyInstaller-compatible)
# ---------------------------------------------------------------------------

def _base_dir():
    """Return the project root, works both in dev and when bundled as .exe."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CONFIG_FILE = os.path.join(_base_dir(), "core", "admin_config.json")

# ---------------------------------------------------------------------------
# Security questions pool
# ---------------------------------------------------------------------------

SECURITY_QUESTIONS = [
    "What is your pet's name?",
    "What city were you born in?",
    "What is your favorite teacher's name?",
    "What was the name of your first school?",
    "What is your mother's maiden name?",
]

# ---------------------------------------------------------------------------
# AuthManager
# ---------------------------------------------------------------------------

class AuthManager:
    """Manages admin password, security question, and file locking."""

    def __init__(self):
        self._locked_handles = []  # open file handles to keep locked
        self._config = self._load_config()

    # ── Config I/O ────────────────────────────────────────────────────────

    def _load_config(self) -> dict:
        if not os.path.exists(CONFIG_FILE):
            return {}
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}

    def _save_config(self):
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self._config, f, indent=2, default=str)

    # ── First-run detection ───────────────────────────────────────────────

    def is_first_run(self) -> bool:
        return not self._config.get("password_hash")

    # ── Password management ───────────────────────────────────────────────

    def set_password(self, plain: str, question_index: int, security_answer: str):
        """Hash and store password + security question on first run."""
        pw_hash = bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()
        ans_hash = bcrypt.hashpw(
            security_answer.strip().lower().encode(), bcrypt.gensalt()
        ).decode()
        self._config.update({
            "password_hash": pw_hash,
            "security_question": SECURITY_QUESTIONS[question_index],
            "security_answer_hash": ans_hash,
            "failed_attempts": 0,
            "lockout_until": None,
            "created_at": datetime.datetime.now().isoformat(),
        })
        self._save_config()

    def verify_password(self, plain: str) -> bool:
        """Verify admin password. Returns False if locked out."""
        if self._is_locked_out():
            return False
        stored = self._config.get("password_hash", "")
        if not stored:
            return False
        ok = bcrypt.checkpw(plain.encode(), stored.encode())
        if ok:
            self._config["failed_attempts"] = 0
            self._config["lockout_until"] = None
            self._save_config()
        else:
            self._config["failed_attempts"] = self._config.get("failed_attempts", 0) + 1
            if self._config["failed_attempts"] >= 5:
                self._config["lockout_until"] = (
                    datetime.datetime.now() + datetime.timedelta(hours=1)
                ).isoformat()
            self._save_config()
        return ok

    def change_password(self, old_pass: str, new_pass: str) -> bool:
        if not self.verify_password(old_pass):
            return False
        pw_hash = bcrypt.hashpw(new_pass.encode(), bcrypt.gensalt()).decode()
        self._config["password_hash"] = pw_hash
        self._save_config()
        return True

    # ── Forgot password (security-question recovery) ─────────────────────

    def get_security_question(self) -> str:
        return self._config.get("security_question", "")

    def forgot_password(self, security_answer: str, new_password: str) -> bool:
        """Verify security answer; if correct, reset password."""
        if self._is_locked_out():
            return False
        stored = self._config.get("security_answer_hash", "")
        if not stored:
            return False
        ok = bcrypt.checkpw(
            security_answer.strip().lower().encode(), stored.encode()
        )
        if ok:
            pw_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
            self._config["password_hash"] = pw_hash
            self._config["failed_attempts"] = 0
            self._config["lockout_until"] = None
            self._save_config()
            return True
        else:
            self._config["failed_attempts"] = self._config.get("failed_attempts", 0) + 1
            if self._config["failed_attempts"] >= 3:
                self._config["lockout_until"] = (
                    datetime.datetime.now() + datetime.timedelta(hours=1)
                ).isoformat()
            self._save_config()
            return False

    def _is_locked_out(self) -> bool:
        until = self._config.get("lockout_until")
        if not until:
            return False
        try:
            lockout_time = datetime.datetime.fromisoformat(until)
            if datetime.datetime.now() < lockout_time:
                return True
            # Lockout expired
            self._config["lockout_until"] = None
            self._config["failed_attempts"] = 0
            self._save_config()
            return False
        except (ValueError, TypeError):
            return False

    def get_lockout_remaining(self) -> int:
        """Return seconds remaining in lockout, or 0."""
        until = self._config.get("lockout_until")
        if not until:
            return 0
        try:
            lockout_time = datetime.datetime.fromisoformat(until)
            remaining = (lockout_time - datetime.datetime.now()).total_seconds()
            return max(0, int(remaining))
        except (ValueError, TypeError):
            return 0

    # ── File locking (prevent edits while running) ────────────────────────

    def lock_config_files(self):
        """Open config and DB files with exclusive access to prevent tampering."""
        files_to_lock = [CONFIG_FILE]
        db_path = os.path.join(_base_dir(), "core", "data.db")
        if os.path.exists(db_path):
            files_to_lock.append(db_path)

        for fpath in files_to_lock:
            if not os.path.exists(fpath):
                continue
            try:
                # Open with shared read but exclusive write
                handle = open(fpath, "r+b")
                # Lock the first byte exclusively using Windows msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                self._locked_handles.append(handle)
            except (IOError, OSError):
                pass  # If we can't lock, continue — better than crashing

    def unlock_config_files(self):
        """Release all file locks on shutdown."""
        for handle in self._locked_handles:
            try:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                handle.close()
            except (IOError, OSError):
                pass
        self._locked_handles.clear()


# ---------------------------------------------------------------------------
# Terminal-based first-run setup (used by main.py)
# ---------------------------------------------------------------------------

def terminal_first_run_setup() -> AuthManager:
    """Interactive terminal setup for first run. Returns configured AuthManager."""
    auth = AuthManager()
    if not auth.is_first_run():
        return auth

    print("\n" + "=" * 60)
    print("  🔐 FOCUS ENGINE PRO — First Run Setup")
    print("=" * 60)
    print("\nYou need to set an Admin Password.")
    print("This password protects your engine from being disabled impulsively.\n")

    while True:
        pw = input("  Set Admin Password (min 4 chars): ").strip()
        if len(pw) < 4:
            print("  ❌ Password too short. Try again.")
            continue
        pw2 = input("  Confirm Password: ").strip()
        if pw != pw2:
            print("  ❌ Passwords don't match. Try again.")
            continue
        break

    print("\n  Now pick a Security Question (for password recovery):\n")
    for i, q in enumerate(SECURITY_QUESTIONS):
        print(f"    [{i + 1}] {q}")

    while True:
        try:
            choice = int(input("\n  Enter choice (1-5): ").strip()) - 1
            if 0 <= choice < len(SECURITY_QUESTIONS):
                break
        except ValueError:
            pass
        print("  ❌ Invalid choice.")

    answer = input(f"\n  Answer: \"{SECURITY_QUESTIONS[choice]}\"\n  > ").strip()
    while not answer:
        answer = input("  ❌ Answer cannot be empty. Try again: ").strip()

    auth.set_password(pw, choice, answer)
    print("\n  ✅ Admin password and security question saved!")
    print("=" * 60 + "\n")
    return auth
