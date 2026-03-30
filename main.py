"""
Focus Engine Pro — Master Orchestrator
Runs all subsystems: DNS Blocker, App Killer, Activity Tracker,
WebSocket API, HTTP Dashboard Server, and Watchdog.
Auto-elevates to Administrator if not already running as admin.
"""

import os
import sys
import time
import ctypes
import threading

# ─── Admin Elevation ──────────────────────────────────────────────────────

def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def elevate():
    """Re-launch the script with admin privileges (UAC prompt)."""
    if is_admin():
        return True
    try:
        script = os.path.abspath(sys.argv[0])
        params = " ".join(sys.argv[1:])
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, f'"{script}" {params}', None, 1
        )
        sys.exit(0)
    except Exception as e:
        print(f"[!] Failed to elevate to admin: {e}")
        print("[!] Please right-click and 'Run as Administrator'.")
        input("Press Enter to exit...")
        sys.exit(1)


# ─── Main ─────────────────────────────────────────────────────────────────

def main():
    # Step 1: Ensure admin privileges
    if not is_admin():
        print("[*] Requesting Administrator privileges...")
        elevate()
        return

    print()
    print("=" * 60)
    print("  🔥 FOCUS ENGINE PRO v1.0")
    print("  Your hardcore productivity guardian")
    print("=" * 60)
    print()

    # Step 2: Initialize database
    from core import database as db
    db.init_db()
    print("[+] Database initialized")

    # Step 3: Auth setup (first run = set password)
    from core.auth import AuthManager, terminal_first_run_setup
    auth = terminal_first_run_setup()
    print("[+] Authentication system ready")

    # Step 4: Watchdog — create scheduled task on first run + protect process
    from core.watchdog import Watchdog
    watchdog = Watchdog()
    if not watchdog.is_task_scheduled():
        watchdog.create_scheduled_task()
    watchdog.protect_process()

    # Step 5: DNS Blocker
    from core.dns_blocker import DNSBlocker
    dns = DNSBlocker()
    dns_setting = db.get_setting("dns_blocking", "on")
    if dns_setting == "on":
        dns.enable_safe_mode()
    # If focus mode was left ON, re-apply incognito block
    if db.get_setting("focus_mode", "off") == "on":
        dns.block_incognito()
    print("[+] DNS Blocker armed")

    # Step 6: App Killer
    from core.app_killer import AppKiller
    killer = AppKiller()

    def run_app_killer():
        while True:
            try:
                killer.hunt_and_kill()
            except Exception as e:
                print(f"  [!] App Killer error: {e}")
            time.sleep(5)

    killer_thread = threading.Thread(target=run_app_killer, daemon=True)
    killer_thread.start()
    print("[+] App Killer radar is LIVE")

    # Step 7: Activity Tracker
    from core.tracker import ActivityTracker
    tracker = ActivityTracker()
    tracker.start()
    print("[+] Activity Tracker running (2-second polling)")

    # Step 8: Lock config files
    auth.lock_config_files()
    print("[+] Config files locked (protected from tampering)")

    # Step 9: Shutdown flag
    shutdown = threading.Event()

    def trigger_shutdown():
        shutdown.set()

    # Step 10: WebSocket API Server
    from core.api_server import start_api_server, start_http_server
    api = start_api_server(
        auth=auth,
        app_killer=killer,
        tracker=tracker,
        dns_blocker=dns,
        port=8765,
        on_shutdown=trigger_shutdown,
    )

    # Step 11: HTTP Dashboard Server
    start_http_server(port=8080)

    # ── Running ───────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("  ✅ ENGINE IS FULLY ARMED!")
    print()
    print("  📊 Dashboard:  http://localhost:8080")
    print("  🔌 WebSocket:  ws://localhost:8765")
    print()
    print("  Press Ctrl+C to request shutdown (requires password)")
    print("=" * 60)
    print()

    try:
        while not shutdown.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Shutdown requested via Ctrl+C...")
        # Ask for password
        for attempt in range(3):
            try:
                password = input("  🔐 Enter Admin Password to shut down: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n  [!] Shutdown cancelled. Engine continues running.")
                # Re-enter the loop
                try:
                    while not shutdown.is_set():
                        time.sleep(1)
                except KeyboardInterrupt:
                    continue
                return

            if auth.verify_password(password):
                print("  ✅ Password verified. Shutting down...")
                break
            else:
                remaining = auth.get_lockout_remaining()
                if remaining > 0:
                    print(f"  ❌ Too many attempts. Locked for {remaining // 60} minutes.")
                    print("  [!] Engine will keep running. Close this terminal if you must.")
                    try:
                        while not shutdown.is_set():
                            time.sleep(1)
                    except KeyboardInterrupt:
                        continue
                    return
                print(f"  ❌ Wrong password. {2 - attempt} attempts remaining.")
        else:
            print("  [!] All attempts failed. Engine continues running.")
            try:
                while not shutdown.is_set():
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
            return

    # ── Graceful Shutdown ─────────────────────────────────────────────
    print("\n[*] Shutting down Focus Engine Pro...")

    # Stop tracker
    tracker.stop()
    print("  [+] Activity Tracker stopped")

    # Restore DNS
    dns.disable_safe_mode()
    dns.unblock_incognito()
    print("  [+] DNS and incognito restored")

    # Unlock files
    auth.unlock_config_files()
    print("  [+] Config files unlocked")

    # Update daily summary one last time
    import datetime
    try:
        db.update_daily_summary(datetime.date.today().isoformat())
    except Exception:
        pass

    print()
    print("=" * 60)
    print("  👋 Focus Engine Pro has been disabled.")
    print("     Good job studying, Atharv! Keep it up!")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()