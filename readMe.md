<div align="center">

<img src="https://img.shields.io/badge/Platform-Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white"/>
<img src="https://img.shields.io/badge/Python-3.8+-3776AB?style=for-the-badge&logo=python&logoColor=white"/>
<img src="https://img.shields.io/badge/Status-Active-brightgreen?style=for-the-badge"/>
<img src="https://img.shields.io/github/stars/atharvotech/Productive-OS?style=for-the-badge&color=yellow"/>

<br/><br/>

# 🧠 Productive-OS (Atharotech)
### *Your AI-Powered Study Partner — Not Just Another Website Blocker*

**The only Windows productivity tool that locks down your entire system, rewards your focus with real points, and fights back when you try to cheat.**

[📥 Download](#-installation--setup) · [🖥️ Dashboard Preview](#-dashboard-preview) · [⭐ Star this Repo](https://github.com/atharvotech/Focus-Engine-Pro) · [🐛 Report a Bug](https://github.com/atharvotech/Focus-Engine-Pro/issues)

</div>

---

## 🤔 Why Focus Engine Pro Is Different

Most focus apps are easy to beat. You close the browser extension, switch to a different browser, or just uninstall the app. Done — distraction wins.

**SATHI does not let that happen.**

Instead of playing nice, it digs deep into your Windows system. It watches every active window, intercepts DNS requests before they reach your browser, scans for background games and kills them, and even tracks what you are listening to on Spotify. It locks itself behind an admin password and a watchdog process that restarts it automatically, even if you force-kill it.

And when you actually study? It **rewards** you — with a token system that unlocks real game time. Focus stops being a punishment. It becomes a game you can win.

---

## ✨ Feature Breakdown

### 🔒 System-Level Lockdown
SATHI does not rely on browser extensions alone. It operates at the OS level — modifying DNS settings, writing to the Windows Registry, and using process-level controls to enforce your session. This means it works across **all browsers, all apps, and all windows** at once.

### 🌐 Family-Safe DNS Filtering (Auto-Setup)
SATHI automatically configures your system DNS to block adult content and harmful websites the moment a focus session starts. No manual configuration needed. It uses the same approach as enterprise-grade parental control systems.

### 🕵️ Full Window & App Monitoring
Every application you open is logged. Idle desktop time is tracked. If a game is detected running silently in the background during a focus session, it is force-closed immediately.

### 🎵 Spotify Listening Activity Tracking
SATHI reads your Spotify activity in real time. Patterns like constant track-skipping or switching playlists are captured and added to your session report — giving you an honest view of how focused you actually were.

### 📊 Screen Time Charts & Analytics Dashboard
A beautiful live dashboard built with Chart.js shows your daily and weekly screen time, productive vs. distracted time, and Spotify activity — all visualized inside a sleek glassmorphism-styled UI.

### 🏆 Token Economy — Earn Game Time by Studying
This is the heart of SATHI. Every focused minute earns **tokens**. Tokens unlock real game time after your session ends. Tokens are stored in a tamper-protected SQLite database, so there is no way to fake your way to a reward.

| Action | Tokens |
|--------|--------|
| Complete a 25-min Pomodoro session | +10 tokens |
| Complete 1 hour of deep work | +30 tokens |
| Unlock 30 min of game time | −15 tokens |
| Attempted bypass detected | −50 tokens (penalty) |

### 🔐 Admin Password & Self-Healing Watchdog
You set a master password during first-run setup. If anyone — including you — tries to stop the engine without the password, a background watchdog process automatically brings it back to life. Forgot your password? The security question recovery flow has you covered.

---

## 💻 Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend Core** | Python — `psutil`, `winreg`, `ctypes`, `threading`, `msvcrt` |
| **Data & Auth** | SQLite3, bcrypt |
| **Real-Time API** | WebSockets (Port 8765) + HTTP Server (Port 8080) |
| **Frontend Dashboard** | HTML5, CSS3 (Glassmorphism), Vanilla JS, Chart.js |
| **Browser Integration** | Chrome Extension — Manifest V3 + Background Service Workers |

---

## 🚀 Installation & Setup

Total setup time: approximately 5 minutes.

### Step 1 — Clone the Repository & Install Dependencies

```bash
git clone https://github.com/yourusername/Focus-Engine-Pro.git
cd Focus-Engine-Pro
pip install -r requirements.txt
```

### Step 2 — Install the Chrome Extension

Open Chrome or Brave and navigate to `chrome://extensions/`. Enable **Developer Mode** using the toggle in the top-right corner, then click **Load unpacked** and select the `extension/` folder from this repository. This connects your browser's tab activity directly to SATHI.

### Step 3 — Launch the Engine as Administrator

> ⚠️ **Critical step.** DNS modification and Windows Registry access both require elevated privileges.

Right-click your terminal or command prompt, select **Run as Administrator**, then execute:

```bash
python main.py
```

On your very first run, an interactive prompt will guide you through creating your **Admin Password** and setting a **Security Recovery Question**.

### Step 4 — Open Your Dashboard

```
http://localhost:8080
```

Your focus engine is live.

---

## 📁 Project Architecture

```
Focus-Engine-Pro/
│
├── core/                   # Python Backend
│   ├── auth.py             # Admin password & bcrypt hashing
│   ├── db.py               # SQLite telemetry & token ledger
│   ├── blocker.py          # DNS & Registry-level site blocking
│   ├── app_killer.py       # Background game detection & termination
│   ├── tracker.py          # Window activity & idle time logging
│   ├── api.py              # WebSocket + HTTP API endpoints
│   └── watchdog.py         # Self-healing process guardian
│
├── dashboard/              # Web UI
│   ├── index.html
│   ├── style.css           # Glassmorphism design system
│   └── charts.js           # Chart.js analytics rendering
│
├── extension/              # Chrome Extension (Manifest V3)
│   ├── manifest.json
│   └── background.js       # Service worker for real-time tab tracking
│
├── requirements.txt
└── main.py                 # Master Orchestrator — entry point
```

---

## 🖥️ Dashboard Preview

> *(Screenshots coming soon — contributions welcome!)*

The dashboard features a live activity feed, token balance widget, interactive screen time charts, Spotify listening graphs, and one-click session controls — all in a dark glassmorphism interface that is designed to feel motivating, not clinical.

---

## 🛠️ Troubleshooting & FAQ

**I forgot my Admin Password. How do I stop the engine?**
On the web dashboard or terminal, select **"Forgot Password"**. You will be asked the Security Question you set up during first-run setup. A correct answer allows you to reset the password and regain full control.

**Incognito Mode is not being blocked.**
Ensure `main.py` was launched with Administrator privileges. SATHI writes to the `HKLM` Windows Registry hive, which is inaccessible to standard user processes and causes silent failures without elevation.

**The dashboard is not loading.**
Check your terminal to confirm that ports `8080` (HTTP) and `8765` (WebSocket) are free. On Windows, run `netstat -ano | findstr :8080` to identify any conflicting process.

**A game is slipping through and not being detected.**
SATHI uses process name matching and heuristic scanning. If a specific game is not being caught, please open a GitHub issue with the executable name and we will add it to the detection list.

---

## 🗺️ Roadmap

- [x] Process tracking & heuristic game killing
- [x] SQLite telemetry & token economy
- [x] Custom Chrome Extension integration
- [x] Admin password & watchdog self-protection
- [x] Family-safe DNS auto-configuration
- [ ] Package the entire Python backend into a single `.exe` using PyInstaller
- [ ] Strict **Pomodoro Mode** with enforced break timers
- [ ] Mobile dashboard companion for viewing stats from your phone
- [ ] Weekly focus reports sent to your email

---

## 🤝 Contributing

All contributions are welcome — whether you are fixing a bug, improving the dashboard, adding games to the detection list, or writing documentation. To contribute, fork the repository, create a feature branch (`git checkout -b feature/YourFeature`), commit your changes, and open a Pull Request.

---

## ⭐ Support the Project

If SATHI helped you study better, focus longer, or simply stopped you from opening Steam at midnight — please give this repository a **star**. It costs nothing and helps more students find the project.

[![Star this repo](https://img.shields.io/github/stars/yourusername/Focus-Engine-Pro?style=social)](https://github.com/yourusername/Focus-Engine-Pro)

---

## ⚠️ Disclaimer

Focus Engine Pro makes real, active changes to your Windows OS — including modifying `HKLM` Registry keys, changing DNS settings via `netsh`, and forcefully terminating processes. **Use at your own risk.** The developers are not responsible for system lockouts or data loss caused by manually tampering with the locked SQLite database while the engine is running. Always use the official admin password flow to stop or modify an active session.

---

<div align="center">
<h2>Made with ❤️ in INDIA By <i>ATHARVOECH-THE WORLD OF INFINTE CREATIVITY</i></h2>
© 2026 Atharvotech(Atharv Shukla). All Rights Reserved. This is a personal project and is currently closed for external distribution or modification.

</div>
