"""
Focus Engine Pro — WebSocket API Server + HTTP Static File Server
Handles all communication between the Dashboard, Chrome Extension, and Python backend.
WebSocket on ws://localhost:8765, HTTP on http://localhost:8080.
"""

import os
import sys
import json
import asyncio
import threading
import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from functools import partial

import websockets

from core import database as db
from core.auth import AuthManager


def _base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ─── HTTP Static File Server (for dashboard) ──────────────────────────────

class DashboardHandler(SimpleHTTPRequestHandler):
    """Serve files from the dashboard/ directory."""

    def __init__(self, *args, directory=None, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def log_message(self, format, *args):
        pass  # Silence HTTP logs

    def end_headers(self):
        # CORS headers for local development
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()


def start_http_server(port: int = 8080):
    """Start the HTTP server for the dashboard in a daemon thread."""
    dashboard_dir = os.path.join(_base_dir(), "dashboard")
    handler = partial(DashboardHandler, directory=dashboard_dir)
    server = HTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"  [+] Dashboard HTTP server running at http://localhost:{port}")
    return server


# ─── WebSocket API Server ─────────────────────────────────────────────────

class APIServer:
    """WebSocket server handling all API commands."""

    def __init__(self, auth: AuthManager, app_killer=None, tracker=None, dns_blocker=None):
        self.auth = auth
        self.app_killer = app_killer
        self.tracker = tracker
        self.dns_blocker = dns_blocker
        self._shutdown_event = asyncio.Event()
        self._clients = set()
        self.on_shutdown = None  # Callback to trigger engine shutdown
        self._event_loop = None  # Store reference to the event loop for cross-thread calls

    async def handler(self, websocket):
        """Handle a single WebSocket connection."""
        self._clients.add(websocket)
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    response = await self._process_command(data)
                    await websocket.send(json.dumps(response))
                except json.JSONDecodeError:
                    await websocket.send(json.dumps({"error": "Invalid JSON"}))
                except Exception as e:
                    await websocket.send(json.dumps({"error": str(e)}))
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._clients.discard(websocket)

    async def broadcast(self, data: dict):
        """Send a message to all connected clients."""
        if self._clients:
            msg = json.dumps(data)
            await asyncio.gather(
                *[client.send(msg) for client in self._clients],
                return_exceptions=True
            )

    async def _process_command(self, data: dict) -> dict:
        """Route incoming commands to appropriate handlers."""
        action = data.get("action", "")

        # ── Read-only commands (no auth required) ─────────────────────
        if action == "get_stats":
            return await self._get_stats(data)

        elif action == "get_hourly":
            date = data.get("date", datetime.date.today().isoformat())
            return {"action": "hourly_data", "data": db.get_hourly_breakdown(date)}

        elif action == "get_top_apps":
            date = data.get("date", datetime.date.today().isoformat())
            limit = data.get("limit", 10)
            return {"action": "top_apps", "data": db.get_top_apps(date, limit)}

        elif action == "get_tokens":
            balance = db.get_token_balance()
            history = db.get_token_history(data.get("date"))
            return {"action": "tokens", "balance": balance, "history": history}

        elif action == "get_focus_mode":
            mode = db.get_setting("focus_mode", "off")
            gaming_min = self.app_killer.get_gaming_minutes() if self.app_killer else 0
            warning = db.get_setting("gaming_warning", "")
            return {
                "action": "focus_mode",
                "mode": mode,
                "gaming_minutes": round(gaming_min, 1),
                "warning": warning,
            }

        elif action == "get_blocked_apps":
            if self.app_killer:
                return {"action": "blocked_apps", **self.app_killer.get_blacklist()}
            return {"action": "blocked_apps", "user_blacklist": [], "user_whitelist": []}

        elif action == "get_engine_status":
            return {
                "action": "engine_status",
                "running": True,
                "dns_enabled": self.dns_blocker.is_enabled() if self.dns_blocker else False,
                "focus_mode": db.get_setting("focus_mode", "off"),
                "token_balance": db.get_token_balance(),
                "uptime": "active",
            }

        elif action == "get_current_activity":
            if self.tracker:
                return {"action": "current_activity", **self.tracker.get_current_activity()}
            return {"action": "current_activity", "app": "Unknown", "category": "other"}

        elif action == "get_spotify":
            today = data.get("date", datetime.date.today().isoformat())
            spotify_time = db.get_spotify_screen_time(today)
            if self.tracker:
                return {
                    "action": "spotify",
                    "history": self.tracker.get_spotify_history(),
                    "listening_seconds": spotify_time,
                }
            return {"action": "spotify", "history": [], "listening_seconds": spotify_time}

        elif action == "get_settings":
            return {"action": "settings", "data": db.get_all_settings()}

        elif action == "get_web_stats":
            date = data.get("date", datetime.date.today().isoformat())
            return {"action": "web_stats", "data": db.get_web_time_stats(date)}

        elif action == "get_web_blocked":
            date = data.get("date", datetime.date.today().isoformat())
            return {"action": "web_blocked", "data": db.get_web_blocked_log(date)}

        elif action == "get_recent_web":
            limit = data.get("limit", 20)
            return {"action": "recent_web", "data": db.get_recent_web_activity(limit)}

        elif action == "get_streak":
            return {"action": "streak", "days": db.get_streak()}

        elif action == "get_monthly":
            year = data.get("year", datetime.date.today().year)
            month = data.get("month", datetime.date.today().month)
            return {"action": "monthly_stats", "data": db.get_monthly_stats(year, month)}

        elif action == "get_yearly":
            year = data.get("year", datetime.date.today().year)
            return {"action": "yearly_stats", "data": db.get_yearly_stats(year)}

        elif action == "get_category_totals":
            date = data.get("date", datetime.date.today().isoformat())
            return {"action": "category_totals", "data": db.get_category_totals(date)}

        # ── Extension data logging (no auth, from Chrome Extension) ───
        elif action == "log_web_time":
            domain = data.get("domain", "")
            url = data.get("url", "")
            title = data.get("title", "")
            seconds = data.get("seconds", 0)
            category = data.get("category", "other")
            if domain and seconds > 0:
                db.log_web_time(domain, url, title, category, seconds)
            return {"action": "ack", "status": "ok"}

        # ── Auth-required commands ────────────────────────────────────
        elif action == "verify_password":
            ok = self.auth.verify_password(data.get("password", ""))
            lockout = self.auth.get_lockout_remaining()
            return {"action": "auth_result", "valid": ok, "lockout_seconds": lockout}

        elif action == "toggle_focus_mode":
            password = data.get("password", "")
            target = data.get("target", "")  # "on" or "off"
            # Turning ON doesn't require password; turning OFF does
            if target == "off":
                if not self.auth.verify_password(password):
                    return {"action": "error", "message": "Wrong password", "lockout_seconds": self.auth.get_lockout_remaining()}
            db.set_setting("focus_mode", target)
            # Toggle incognito based on focus mode
            if self.dns_blocker:
                if target == "on":
                    self.dns_blocker.block_incognito()
                else:
                    self.dns_blocker.unblock_incognito()
            return {"action": "focus_mode_changed", "mode": target}

        elif action == "disable_engine":
            password = data.get("password", "")
            if not self.auth.verify_password(password):
                return {"action": "error", "message": "Wrong password", "lockout_seconds": self.auth.get_lockout_remaining()}
            # Trigger shutdown
            if self.on_shutdown:
                self.on_shutdown()
            return {"action": "engine_disabled", "status": "shutting_down"}

        elif action == "update_blocked_apps":
            password = data.get("password", "")
            if not self.auth.verify_password(password):
                return {"action": "error", "message": "Wrong password"}
            apps = data.get("apps", [])
            if self.app_killer:
                self.app_killer.update_blacklist(apps)
            return {"action": "blocked_apps_updated"}

        elif action == "update_whitelist":
            password = data.get("password", "")
            if not self.auth.verify_password(password):
                return {"action": "error", "message": "Wrong password"}
            apps = data.get("apps", [])
            if self.app_killer:
                self.app_killer.update_whitelist(apps)
            return {"action": "whitelist_updated"}

        elif action == "toggle_adult_block":
            password = data.get("password", "")
            if not self.auth.verify_password(password):
                return {"action": "error", "message": "Wrong password"}
            enable = data.get("enable", True)
            if self.dns_blocker:
                if enable:
                    self.dns_blocker.enable_safe_mode()
                    db.set_setting("dns_blocking", "on")
                else:
                    self.dns_blocker.disable_safe_mode()
                    db.set_setting("dns_blocking", "off")
            return {"action": "adult_block_changed", "enabled": enable}

        elif action == "change_password":
            old = data.get("old", "")
            new = data.get("new", "")
            if len(new) < 4:
                return {"action": "error", "message": "Password must be at least 4 characters"}
            ok = self.auth.change_password(old, new)
            return {"action": "password_changed" if ok else "error",
                    "message": "Password changed" if ok else "Wrong old password"}

        elif action == "forgot_password":
            answer = data.get("answer", "")
            new_password = data.get("new_password", "")
            if len(new_password) < 4:
                return {"action": "error", "message": "Password must be at least 4 characters"}
            ok = self.auth.forgot_password(answer, new_password)
            lockout = self.auth.get_lockout_remaining()
            return {
                "action": "password_reset" if ok else "error",
                "message": "Password has been reset!" if ok else "Wrong answer",
                "lockout_seconds": lockout,
            }

        elif action == "get_security_question":
            return {"action": "security_question", "question": self.auth.get_security_question()}

        elif action == "spend_tokens":
            password = data.get("password", "")
            amount = data.get("amount", 0)
            if not self.auth.verify_password(password):
                return {"action": "error", "message": "Wrong password"}
            if amount <= 0:
                return {"action": "error", "message": "Invalid amount"}
            balance = db.get_token_balance()
            if amount > balance:
                return {"action": "error", "message": f"Insufficient tokens. Balance: {balance}"}
            db.spend_tokens(amount, "manual_spend")
            return {"action": "tokens_spent", "amount": amount, "new_balance": db.get_token_balance()}

        elif action == "update_settings":
            password = data.get("password", "")
            if not self.auth.verify_password(password):
                return {"action": "error", "message": "Wrong password"}
            settings = data.get("settings", {})
            for k, v in settings.items():
                if k not in ("password_hash", "security_answer_hash"):  # Protect sensitive keys
                    db.set_setting(k, str(v))
            return {"action": "settings_updated"}

        else:
            return {"action": "error", "message": f"Unknown action: {action}"}

    async def _get_stats(self, data: dict) -> dict:
        """Get stats for a given period."""
        period = data.get("period", "day")
        date = data.get("date", datetime.date.today().isoformat())

        if period == "day":
            screen = db.get_screen_time_stats(date)
            web = db.get_web_time_stats(date)
            categories = db.get_category_totals(date)
            hourly = db.get_hourly_breakdown(date)
            tokens = db.get_token_balance()
            top = db.get_top_apps(date)
            streak = db.get_streak()
            total_sec = sum(categories.values())
            return {
                "action": "stats",
                "period": "day",
                "date": date,
                "total_screen_seconds": total_sec,
                "categories": categories,
                "screen_time": screen,
                "web_time": web,
                "hourly": hourly,
                "top_apps": top,
                "token_balance": tokens,
                "streak": streak,
            }

        elif period == "month":
            year = data.get("year", datetime.date.today().year)
            month = data.get("month", datetime.date.today().month)
            return {
                "action": "stats",
                "period": "month",
                "data": db.get_monthly_stats(year, month),
            }

        elif period == "year":
            year = data.get("year", datetime.date.today().year)
            return {
                "action": "stats",
                "period": "year",
                "data": db.get_yearly_stats(year),
            }

        return {"action": "error", "message": "Invalid period. Use: day, month, year"}


# ─── Start WebSocket Server ───────────────────────────────────────────────

def start_api_server(auth: AuthManager, app_killer=None, tracker=None, dns_blocker=None,
                     port: int = 8765, on_shutdown=None):
    """Start the WebSocket API server in a new thread with its own event loop."""
    api = APIServer(auth, app_killer, tracker, dns_blocker)
    api.on_shutdown = on_shutdown

    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        api._event_loop = loop

        async def _serve():
            async with websockets.serve(api.handler, "127.0.0.1", port):
                print(f"  [+] WebSocket API server running at ws://localhost:{port}")
                await asyncio.Future()  # Run forever

        loop.run_until_complete(_serve())

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    # --- Server-Push: broadcast stats after tracker flushes ---
    def on_tracker_flush():
        """Called from the tracker thread after data is flushed to DB.
        Schedules a broadcast of updated stats to all dashboard clients."""
        if not api._event_loop or not api._clients:
            return
        try:
            asyncio.run_coroutine_threadsafe(_broadcast_update(api), api._event_loop)
        except Exception:
            pass

    async def _broadcast_update(api_server):
        """Build fresh stats payload and broadcast to all connected clients."""
        try:
            today = datetime.date.today().isoformat()
            categories = db.get_category_totals(today)
            total_sec = sum(categories.values())
            tokens = db.get_token_balance()
            streak = db.get_streak()
            hourly = db.get_hourly_breakdown(today)

            stats_msg = {
                "action": "stats",
                "period": "day",
                "date": today,
                "total_screen_seconds": total_sec,
                "categories": categories,
                "screen_time": db.get_screen_time_stats(today),
                "web_time": db.get_web_time_stats(today),
                "hourly": hourly,
                "top_apps": db.get_top_apps(today),
                "token_balance": tokens,
                "streak": streak,
            }
            await api_server.broadcast(stats_msg)

            # Also push token balance
            token_history = db.get_token_history(today)
            await api_server.broadcast({
                "action": "tokens",
                "balance": tokens,
                "history": token_history,
            })

            # Push current activity
            if api_server.tracker:
                activity = api_server.tracker.get_current_activity()
                await api_server.broadcast({"action": "current_activity", **activity})

                # Push Spotify
                spotify_time = db.get_spotify_screen_time(today)
                await api_server.broadcast({
                    "action": "spotify",
                    "history": api_server.tracker.get_spotify_history(),
                    "listening_seconds": spotify_time,
                })

            # Push category totals
            await api_server.broadcast({
                "action": "category_totals",
                "data": categories,
            })

            # Push recent web
            await api_server.broadcast({
                "action": "recent_web",
                "data": db.get_recent_web_activity(20),
            })
        except Exception as e:
            print(f"  [!] Broadcast error: {e}")

    # Hook the tracker's on_flush callback
    if tracker:
        tracker.on_flush = on_tracker_flush

    return api
