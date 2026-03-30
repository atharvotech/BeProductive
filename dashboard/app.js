/**
 * Focus Engine Pro — Dashboard Application
 * 
 * Connects to WebSocket, renders charts with Chart.js,
 * manages navigation, settings, and the password modal.
 * 
 * Architecture: Server-Push — the backend broadcasts updated data
 * after each tracker flush (~30 seconds). No client-side polling needed.
 */

// ═══════════════════════════════════════════════════════════
// Configuration
// ═══════════════════════════════════════════════════════════

const WS_URL = "ws://localhost:8765";
const CATEGORY_COLORS = {
    study:         { bg: "rgba(16, 185, 129, 0.7)",  border: "#10b981" },
    gaming:        { bg: "rgba(239, 68, 68, 0.7)",   border: "#ef4444" },
    social:        { bg: "rgba(236, 72, 153, 0.7)",  border: "#ec4899" },
    entertainment: { bg: "rgba(124, 58, 237, 0.7)",  border: "#7c3aed" },
    productivity:  { bg: "rgba(6, 182, 212, 0.7)",   border: "#06b6d4" },
    idle:          { bg: "rgba(255, 255, 255, 0.1)",  border: "#555" },
    other:         { bg: "rgba(245, 158, 11, 0.7)",  border: "#f59e0b" },
};

// ═══════════════════════════════════════════════════════════
// WebSocket Connection
// ═══════════════════════════════════════════════════════════

let ws = null;
let wsConnected = false;
let reconnectDelay = 1000;
let reconnectTimer = null;

function connectWebSocket() {
    if (ws && ws.readyState === WebSocket.OPEN) return;

    showConnectionBanner(true);

    try {
        ws = new WebSocket(WS_URL);

        ws.onopen = () => {
            wsConnected = true;
            reconnectDelay = 1000;
            updateEngineStatus(true);
            showConnectionBanner(false);
            console.log("[Dashboard] WebSocket connected — server will push updates");
            // Request initial data once; server will push updates after each flush
            refreshAllData();
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                handleMessage(data);
            } catch (e) {
                console.error("Parse error:", e);
            }
        };

        ws.onclose = () => {
            wsConnected = false;
            updateEngineStatus(false);
            showConnectionBanner(true);
            scheduleReconnect();
        };

        ws.onerror = () => {
            wsConnected = false;
        };
    } catch (e) {
        scheduleReconnect();
    }
}

function scheduleReconnect() {
    if (reconnectTimer) clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(() => {
        reconnectDelay = Math.min(reconnectDelay * 2, 15000);
        connectWebSocket();
    }, reconnectDelay);
}

function sendWS(data) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(data));
    }
}

function updateEngineStatus(active) {
    const indicator = document.getElementById("engine-status-indicator");
    if (!indicator) return;
    const dot = indicator.querySelector(".status-dot");
    const text = indicator.querySelector(".status-text");
    if (active) {
        dot.classList.add("active");
        text.textContent = "Engine Active";
    } else {
        dot.classList.remove("active");
        text.textContent = "Disconnected";
    }
}

function showConnectionBanner(show) {
    const banner = document.getElementById("connection-banner");
    if (!banner) return;
    banner.classList.toggle("hidden", !show);
}

// ═══════════════════════════════════════════════════════════
// Message Handler
// ═══════════════════════════════════════════════════════════

function handleMessage(data) {
    switch (data.action) {
        case "stats":
            renderStats(data);
            break;
        case "tokens":
            renderTokens(data);
            break;
        case "focus_mode":
            updateFocusMode(data);
            break;
        case "focus_mode_changed":
            updateFocusMode(data);
            showToast(`Focus Mode ${data.mode === "on" ? "enabled 🎯" : "disabled"}`, "success");
            break;
        case "current_activity":
            renderLiveActivity(data);
            break;
        case "hourly_data":
            renderHeatmap(data.data);
            break;
        case "top_apps":
            renderTopApps(data.data);
            break;
        case "web_stats":
            renderWebStats(data.data);
            break;
        case "web_blocked":
            renderBlockedLog(data.data);
            break;
        case "recent_web":
            renderRecentWeb(data.data);
            break;
        case "spotify":
            renderSpotifyHistory(data.history, data.listening_seconds);
            break;
        case "streak":
            animateNumber("stat-streak", data.days);
            break;
        case "blocked_apps":
            renderBlockedApps(data);
            break;
        case "settings":
            loadSettings(data.data);
            break;
        case "category_totals":
            renderCategoryDonut(data.data);
            break;
        case "monthly_stats":
        case "yearly_stats":
            renderPeriodChart(data);
            break;
        case "engine_status":
            updateEngineStatus(data.running);
            break;
        case "auth_result":
            handleAuthResult(data);
            break;
        case "error":
            handleError(data);
            break;
        case "engine_disabled":
            showToast("Engine shutting down...", "info");
            setTimeout(() => { updateEngineStatus(false); }, 1000);
            break;
        case "password_changed":
            showToast("Password changed successfully! ✅", "success");
            closeModal();
            break;
        case "password_reset":
            showToast("Password has been reset! ✅", "success");
            closeModal();
            break;
        case "blocked_apps_updated":
        case "whitelist_updated":
            showToast("App list updated ✅", "success");
            break;
        case "adult_block_changed":
            showToast(`Adult content blocking ${data.enabled ? "enabled" : "disabled"}`, "success");
            break;
        case "settings_updated":
            showToast("Settings saved ✅", "success");
            break;
        case "tokens_spent":
            showToast(`Spent ${data.amount} tokens`, "success");
            sendWS({ action: "get_tokens" });
            break;
        case "security_question":
            showSecurityQuestion(data.question);
            break;
        case "ack":
            break;
        default:
            console.log("Unknown message:", data);
    }
}

function handleAuthResult(data) {
    if (data.valid) {
        if (currentModalCallback) {
            currentModalCallback(true);
            currentModalCallback = null;
        }
    } else {
        showModalError(data.lockout_seconds > 0
            ? `Too many attempts. Locked for ${Math.ceil(data.lockout_seconds / 60)} minutes.`
            : "Wrong password. Try again.");
    }
}

function handleError(data) {
    if (data.lockout_seconds > 0) {
        showModalError(`Locked out for ${Math.ceil(data.lockout_seconds / 60)} minutes.`);
    } else {
        showModalError(data.message || "An error occurred");
    }
}

// ═══════════════════════════════════════════════════════════
// Data Refresh — only on initial connect & page navigation
// Server pushes updates automatically after each tracker flush
// ═══════════════════════════════════════════════════════════

function refreshAllData() {
    const today = new Date().toISOString().split("T")[0];
    sendWS({ action: "get_stats", period: "day", date: today });
    sendWS({ action: "get_tokens" });
    sendWS({ action: "get_focus_mode" });
    sendWS({ action: "get_current_activity" });
    sendWS({ action: "get_hourly", date: today });
    sendWS({ action: "get_top_apps", date: today });
    sendWS({ action: "get_streak" });
    sendWS({ action: "get_category_totals", date: today });
    sendWS({ action: "get_web_stats", date: today });
    sendWS({ action: "get_web_blocked", date: today });
    sendWS({ action: "get_recent_web" });
    sendWS({ action: "get_spotify" });
    sendWS({ action: "get_settings" });
    sendWS({ action: "get_blocked_apps" });
}

// No periodic polling needed — server pushes data on change.
// Only poll current_activity every 3s for the live feed (minimal).
setInterval(() => {
    if (wsConnected) {
        sendWS({ action: "get_current_activity" });
    }
}, 3000);

// ═══════════════════════════════════════════════════════════
// Helper Functions
// ═══════════════════════════════════════════════════════════

function formatTime(seconds) {
    if (!seconds || seconds < 0) return "0s";
    if (seconds < 60) return `${Math.round(seconds)}s`;
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
}

function animateNumber(elementId, target) {
    const el = document.getElementById(elementId);
    if (!el) return;
    const current = parseInt(el.textContent) || 0;
    if (current === target) return;

    const duration = 600;
    const start = performance.now();

    function update(now) {
        const elapsed = now - start;
        const progress = Math.min(elapsed / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3); // ease out cubic
        const value = Math.round(current + (target - current) * eased);
        el.textContent = value;
        if (progress < 1) requestAnimationFrame(update);
    }
    requestAnimationFrame(update);
}

function animateTimeValue(elementId, totalSeconds) {
    const el = document.getElementById(elementId);
    if (!el) return;
    el.textContent = formatTime(totalSeconds);
    // Remove shimmer on first real data
    el.classList.remove("shimmer-text");
}

// ═══════════════════════════════════════════════════════════
// Render: Overview Stats
// ═══════════════════════════════════════════════════════════

function renderStats(data) {
    if (data.period !== "day") return;

    const cats = data.categories || {};
    const totalScreen = data.total_screen_seconds || 0;
    const studyTime = cats.study || 0;
    const tokenBalance = data.token_balance || 0;
    const streak = data.streak || 0;

    animateTimeValue("stat-study-time", studyTime);
    animateTimeValue("stat-screen-time", totalScreen);
    animateNumber("stat-tokens", tokenBalance);
    animateNumber("stat-streak", streak);

    // Daily activity bar chart
    renderDailyActivityChart(data.hourly || []);
}

// ═══════════════════════════════════════════════════════════
// Charts
// ═══════════════════════════════════════════════════════════

let dailyActivityChart = null;
let categoryDonutChart = null;
let topAppsChart = null;
let topWebsitesChart = null;
let webCategoriesChart = null;
let tokenHistoryChart = null;

// Chart.js global defaults
Chart.defaults.color = "rgba(240, 240, 245, 0.6)";
Chart.defaults.borderColor = "rgba(255, 255, 255, 0.06)";
Chart.defaults.font.family = "'Inter', sans-serif";

function renderDailyActivityChart(hourly) {
    const ctx = document.getElementById("chart-daily-activity");
    const emptyState = document.getElementById("daily-chart-empty");
    if (!ctx) return;

    const hasData = hourly.some(h =>
        (h.study || 0) + (h.gaming || 0) + (h.social || 0) +
        (h.entertainment || 0) + (h.productivity || 0) + (h.other || 0) > 0
    );

    if (!hasData && emptyState) {
        emptyState.classList.remove("hidden");
        ctx.style.display = "none";
        return;
    }
    if (emptyState) emptyState.classList.add("hidden");
    ctx.style.display = "block";

    const labels = hourly.map(h => `${h.hour}:00`);
    const categories = ["study", "gaming", "social", "entertainment", "productivity", "other", "idle"];

    const datasets = categories.map(cat => ({
        label: cat.charAt(0).toUpperCase() + cat.slice(1),
        data: hourly.map(h => Math.round((h[cat] || 0) / 60)),
        backgroundColor: CATEGORY_COLORS[cat]?.bg || "rgba(255,255,255,0.1)",
        borderColor: CATEGORY_COLORS[cat]?.border || "#555",
        borderWidth: 1,
        borderRadius: 3,
    }));

    if (dailyActivityChart) {
        dailyActivityChart.data.labels = labels;
        dailyActivityChart.data.datasets = datasets;
        dailyActivityChart.update("none");
    } else {
        dailyActivityChart = new Chart(ctx, {
            type: "bar",
            data: { labels, datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: { stacked: true, grid: { display: false }, ticks: { font: { size: 10 } } },
                    y: { stacked: true, title: { display: true, text: "Minutes" }, ticks: { font: { size: 10 } } },
                },
                plugins: {
                    legend: { position: "top", labels: { boxWidth: 10, padding: 12, font: { size: 11 } } },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y}m`,
                        },
                    },
                },
                interaction: { mode: "index", intersect: false },
            },
        });
    }
}

function renderCategoryDonut(categories) {
    const ctx = document.getElementById("chart-category-donut");
    const emptyState = document.getElementById("category-chart-empty");
    if (!ctx) return;

    const filtered = Object.entries(categories).filter(([_, v]) => v > 0);

    if (filtered.length === 0) {
        if (emptyState) emptyState.classList.remove("hidden");
        ctx.style.display = "none";
        return;
    }
    if (emptyState) emptyState.classList.add("hidden");
    ctx.style.display = "block";

    const labels = filtered.map(([k]) => k.charAt(0).toUpperCase() + k.slice(1));
    const values = filtered.map(([_, v]) => Math.round(v / 60));
    const colors = filtered.map(([k]) => CATEGORY_COLORS[k]?.bg || "rgba(255,255,255,0.1)");
    const borders = filtered.map(([k]) => CATEGORY_COLORS[k]?.border || "#555");

    if (categoryDonutChart) {
        categoryDonutChart.data.labels = labels;
        categoryDonutChart.data.datasets[0].data = values;
        categoryDonutChart.data.datasets[0].backgroundColor = colors;
        categoryDonutChart.data.datasets[0].borderColor = borders;
        categoryDonutChart.update("none");
    } else {
        categoryDonutChart = new Chart(ctx, {
            type: "doughnut",
            data: {
                labels,
                datasets: [{
                    data: values,
                    backgroundColor: colors,
                    borderColor: borders,
                    borderWidth: 2,
                    hoverOffset: 6,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: "65%",
                plugins: {
                    legend: { position: "bottom", labels: { boxWidth: 10, padding: 10, font: { size: 11 } } },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => `${ctx.label}: ${ctx.parsed}m`,
                        },
                    },
                },
            },
        });
    }
}

function renderTopApps(apps) {
    const ctx = document.getElementById("chart-top-apps");
    const emptyState = document.getElementById("top-apps-empty");
    if (!ctx) return;

    if (!apps || apps.length === 0) {
        if (emptyState) emptyState.classList.remove("hidden");
        ctx.style.display = "none";
        const tableContainer = document.getElementById("app-usage-table");
        if (tableContainer) tableContainer.innerHTML = `<p class="empty-text">No usage data yet. The tracker logs data every 30 seconds.</p>`;
        return;
    }
    if (emptyState) emptyState.classList.add("hidden");
    ctx.style.display = "block";

    const labels = apps.map(a => a.app_name.replace(".exe", ""));
    const values = apps.map(a => Math.round(a.total_sec / 60));
    const colors = apps.map(a => CATEGORY_COLORS[a.category]?.bg || "rgba(255,255,255,0.1)");

    if (topAppsChart) {
        topAppsChart.data.labels = labels;
        topAppsChart.data.datasets[0].data = values;
        topAppsChart.data.datasets[0].backgroundColor = colors;
        topAppsChart.update("none");
    } else {
        topAppsChart = new Chart(ctx, {
            type: "bar",
            data: {
                labels,
                datasets: [{
                    label: "Minutes",
                    data: values,
                    backgroundColor: colors,
                    borderRadius: 6,
                    barThickness: 24,
                }],
            },
            options: {
                indexAxis: "y",
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: { grid: { display: false }, title: { display: true, text: "Minutes" } },
                    y: { grid: { display: false }, ticks: { font: { size: 11 } } },
                },
                plugins: { legend: { display: false } },
            },
        });
    }

    // Also render the table
    const tableContainer = document.getElementById("app-usage-table");
    if (tableContainer && apps.length > 0) {
        let html = `<table class="data-table">
            <thead><tr><th>App</th><th>Category</th><th>Time</th></tr></thead><tbody>`;
        apps.forEach(a => {
            html += `<tr>
                <td>${a.app_name}</td>
                <td><span class="activity-category ${a.category}">${a.category}</span></td>
                <td>${formatTime(a.total_sec)}</td>
            </tr>`;
        });
        html += `</tbody></table>`;
        tableContainer.innerHTML = html;
    }
}

function renderWebStats(webData) {
    const ctx = document.getElementById("chart-top-websites");
    const emptyState = document.getElementById("web-chart-empty");
    if (!ctx) return;

    if (!webData || webData.length === 0) {
        if (emptyState) emptyState.classList.remove("hidden");
        ctx.style.display = "none";
        // Hide web categories chart too
        const catCtx = document.getElementById("chart-web-categories");
        const catEmpty = document.getElementById("web-cat-empty");
        if (catCtx) catCtx.style.display = "none";
        if (catEmpty) catEmpty.classList.remove("hidden");
        return;
    }
    if (emptyState) emptyState.classList.add("hidden");
    ctx.style.display = "block";

    const top = webData.slice(0, 10);
    const labels = top.map(w => w.domain);
    const values = top.map(w => Math.round(w.total_sec / 60));
    const colors = top.map(w => CATEGORY_COLORS[w.category]?.bg || CATEGORY_COLORS.other.bg);

    if (topWebsitesChart) {
        topWebsitesChart.data.labels = labels;
        topWebsitesChart.data.datasets[0].data = values;
        topWebsitesChart.data.datasets[0].backgroundColor = colors;
        topWebsitesChart.update("none");
    } else {
        topWebsitesChart = new Chart(ctx, {
            type: "bar",
            data: {
                labels,
                datasets: [{
                    label: "Minutes",
                    data: values,
                    backgroundColor: colors,
                    borderRadius: 6,
                    barThickness: 22,
                }],
            },
            options: {
                indexAxis: "y",
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: { grid: { display: false }, title: { display: true, text: "Minutes" } },
                    y: { grid: { display: false }, ticks: { font: { size: 11 } } },
                },
                plugins: { legend: { display: false } },
            },
        });
    }

    // Web categories donut
    const catCtx = document.getElementById("chart-web-categories");
    const catEmpty = document.getElementById("web-cat-empty");
    if (catCtx) {
        const catMap = {};
        webData.forEach(w => {
            catMap[w.category] = (catMap[w.category] || 0) + w.total_sec;
        });
        const catEntries = Object.entries(catMap).filter(([_, v]) => v > 0);

        if (catEntries.length === 0) {
            catCtx.style.display = "none";
            if (catEmpty) catEmpty.classList.remove("hidden");
            return;
        }
        catCtx.style.display = "block";
        if (catEmpty) catEmpty.classList.add("hidden");

        if (webCategoriesChart) {
            webCategoriesChart.data.labels = catEntries.map(([k]) => k);
            webCategoriesChart.data.datasets[0].data = catEntries.map(([_, v]) => Math.round(v / 60));
            webCategoriesChart.update("none");
        } else {
            webCategoriesChart = new Chart(catCtx, {
                type: "doughnut",
                data: {
                    labels: catEntries.map(([k]) => k),
                    datasets: [{
                        data: catEntries.map(([_, v]) => Math.round(v / 60)),
                        backgroundColor: catEntries.map(([k]) => CATEGORY_COLORS[k]?.bg || CATEGORY_COLORS.other.bg),
                        borderWidth: 1,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: "60%",
                    plugins: { legend: { position: "bottom", labels: { boxWidth: 10, font: { size: 10 } } } },
                },
            });
        }
    }
}

function renderBlockedLog(blocked) {
    const container = document.getElementById("blocked-log");
    if (!container) return;

    if (!blocked || blocked.length === 0) {
        container.innerHTML = `<p class="empty-text">No blocked attempts today 🎉</p>`;
        return;
    }

    let html = `<table class="data-table">
        <thead><tr><th>Time</th><th>Domain</th><th>URL</th></tr></thead><tbody>`;
    blocked.forEach(b => {
        const time = b.timestamp ? new Date(b.timestamp).toLocaleTimeString() : "";
        html += `<tr>
            <td>${time}</td>
            <td>${b.domain}</td>
            <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${b.url}</td>
        </tr>`;
    });
    html += `</tbody></table>`;
    container.innerHTML = html;
}

// ─── Recent Websites (overview + web activity) ───────────────────────────

function renderRecentWeb(data) {
    // Render in overview
    const overviewContainer = document.getElementById("recent-websites");
    // Render in web activity page
    const webContainer = document.getElementById("recent-web-table");

    const html = buildRecentWebHTML(data);
    if (overviewContainer) overviewContainer.innerHTML = html;
    if (webContainer) webContainer.innerHTML = html;
}

function buildRecentWebHTML(data) {
    if (!data || data.length === 0) {
        return `<p class="empty-text">No web activity recorded yet. Make sure the Chrome extension is installed and syncing.</p>`;
    }

    let html = `<table class="data-table">
        <thead><tr><th>Time</th><th>Domain</th><th>Page</th><th>Category</th><th>Time</th></tr></thead><tbody>`;
    data.forEach(w => {
        const time = w.timestamp ? new Date(w.timestamp).toLocaleTimeString() : "";
        const title = (w.page_title || "").substring(0, 50) + ((w.page_title || "").length > 50 ? "…" : "");
        html += `<tr>
            <td class="text-muted">${time}</td>
            <td><strong>${w.domain}</strong></td>
            <td class="text-ellipsis">${title}</td>
            <td><span class="activity-category ${w.category}">${w.category}</span></td>
            <td>${formatTime(w.seconds || 0)}</td>
        </tr>`;
    });
    html += `</tbody></table>`;
    return html;
}

// ─── Heatmap ─────────────────────────────────────────────────────────────

function renderHeatmap(hourly) {
    const container = document.getElementById("hourly-heatmap");
    if (!container) return;

    let html = '<div class="hourly-heatmap">';
    hourly.forEach(h => {
        const total = (h.study || 0) + (h.gaming || 0) + (h.social || 0) +
                      (h.entertainment || 0) + (h.productivity || 0) + (h.other || 0);
        const intensity = Math.min(total / 3600, 1);

        const cats = { study: h.study || 0, gaming: h.gaming || 0, entertainment: h.entertainment || 0 };
        const dominant = Object.entries(cats).sort((a, b) => b[1] - a[1])[0];
        let color;
        if (total === 0) {
            color = "rgba(255,255,255,0.03)";
        } else if (dominant[0] === "study") {
            color = `rgba(16, 185, 129, ${0.15 + intensity * 0.65})`;
        } else if (dominant[0] === "gaming") {
            color = `rgba(239, 68, 68, ${0.15 + intensity * 0.65})`;
        } else {
            color = `rgba(124, 58, 237, ${0.15 + intensity * 0.65})`;
        }

        html += `<div class="heatmap-cell" style="background:${color}">
            <div class="tooltip">${h.hour}:00 — ${formatTime(total)}</div>
        </div>`;
    });
    html += '</div>';

    html += '<div class="heatmap-labels">';
    for (let i = 0; i < 24; i++) {
        html += `<div class="heatmap-label">${i}</div>`;
    }
    html += '</div>';

    container.innerHTML = html;
}

// ─── Live Activity ───────────────────────────────────────────────────────

const activityHistory = [];

function renderLiveActivity(data) {
    const container = document.getElementById("live-activity");
    if (!container) return;

    // Deduplicate consecutive same-app entries
    const lastItem = activityHistory[0];
    if (lastItem && lastItem.app === data.app && lastItem.title === (data.title || "").substring(0, 80)) {
        return; // Same as last, skip
    }

    activityHistory.unshift({
        app: data.app || "Unknown",
        title: (data.title || "").substring(0, 80),
        category: data.category || "other",
        time: new Date().toLocaleTimeString(),
    });

    if (activityHistory.length > 20) activityHistory.pop();

    container.innerHTML = activityHistory.map(a => `
        <div class="activity-item">
            <div class="activity-details">
                <span class="activity-app">${a.app}</span>
                <span class="activity-title">${a.title ? " — " + a.title : ""}</span>
            </div>
            <div class="activity-meta">
                <span class="activity-time">${a.time}</span>
                <span class="activity-category ${a.category}">${a.category}</span>
            </div>
        </div>
    `).join("");

    // Update Spotify "Now Playing" if applicable
    if (data.spotify && data.spotify.playing) {
        const el = document.getElementById("stat-now-playing");
        if (el) el.textContent = `${data.spotify.track} — ${data.spotify.artist}`;
        // Show equalizer animation
        const eq = document.getElementById("equalizer-anim");
        if (eq) eq.classList.add("playing");
    } else {
        const eq = document.getElementById("equalizer-anim");
        if (eq) eq.classList.remove("playing");
    }
}

// ─── Spotify ─────────────────────────────────────────────────────────────

function renderSpotifyHistory(history, listeningSeconds) {
    const container = document.getElementById("spotify-history");
    if (!container) return;

    // Update listening time stat
    const timeEl = document.getElementById("stat-spotify-time");
    if (timeEl && listeningSeconds !== undefined) {
        timeEl.textContent = formatTime(listeningSeconds);
    }

    if (!history || history.length === 0) {
        container.innerHTML = `<p class="empty-text">No Spotify tracks recorded yet 🎵<br><small>Open Spotify and it will be tracked automatically via the window title.</small></p>`;
        return;
    }

    // Render in REVERSE order (most recent first) — history comes oldest-first from backend
    const reversed = [...history].reverse();

    container.innerHTML = reversed.map((t, i) => `
        <div class="track-item ${i === 0 ? 'now-playing' : ''}">
            <div class="track-icon-container">
                ${i === 0 ? '<div class="mini-equalizer"><span></span><span></span><span></span></div>' : '<span class="track-icon">🎵</span>'}
            </div>
            <div class="track-info">
                <div class="track-name">${t.track || "Unknown Track"}</div>
                <div class="track-artist">${t.artist || "Unknown Artist"}</div>
            </div>
            <div class="track-meta">
                ${t.duration ? `<span class="track-duration">${formatTime(t.duration)}</span>` : ''}
                <span class="track-time">${t.time ? new Date(t.time).toLocaleTimeString() : ""}</span>
            </div>
        </div>
    `).join("");
}

// ─── Tokens ──────────────────────────────────────────────────────────────

function renderTokens(data) {
    animateNumber("stat-tokens", data.balance || 0);
    animateNumber("token-balance-large", data.balance || 0);

    const history = data.history || [];
    renderTokenLog(history);
    renderTokenChart(history);
}

function renderTokenLog(history) {
    const container = document.getElementById("token-log");
    if (!container) return;

    if (history.length === 0) {
        container.innerHTML = `<p class="empty-text">No token transactions yet</p>`;
        return;
    }

    let html = `<table class="data-table">
        <thead><tr><th>Time</th><th>Type</th><th>Amount</th><th>Reason</th></tr></thead><tbody>`;
    history.slice(0, 50).forEach(t => {
        const time = t.timestamp ? new Date(t.timestamp).toLocaleTimeString() : "";
        const type = t.earned > 0 ? "Earned" : "Spent";
        const amount = t.earned > 0 ? `+${t.earned}` : `-${t.spent}`;
        const color = t.earned > 0 ? "var(--accent-green)" : "var(--accent-red)";
        html += `<tr>
            <td>${time}</td>
            <td>${type}</td>
            <td style="color:${color}; font-weight:600;">${amount}</td>
            <td>${t.reason || ""}</td>
        </tr>`;
    });
    html += `</tbody></table>`;
    container.innerHTML = html;
}

function renderTokenChart(history) {
    const ctx = document.getElementById("chart-token-history");
    if (!ctx || history.length === 0) return;

    const byDate = {};
    history.forEach(t => {
        if (!byDate[t.date]) byDate[t.date] = { earned: 0, spent: 0 };
        byDate[t.date].earned += t.earned || 0;
        byDate[t.date].spent += t.spent || 0;
    });

    const dates = Object.keys(byDate).sort().slice(-14);
    const earned = dates.map(d => byDate[d].earned);
    const spent = dates.map(d => -byDate[d].spent);

    if (tokenHistoryChart) {
        tokenHistoryChart.data.labels = dates;
        tokenHistoryChart.data.datasets[0].data = earned;
        tokenHistoryChart.data.datasets[1].data = spent;
        tokenHistoryChart.update("none");
    } else {
        tokenHistoryChart = new Chart(ctx, {
            type: "bar",
            data: {
                labels: dates,
                datasets: [
                    {
                        label: "Earned",
                        data: earned,
                        backgroundColor: "rgba(16, 185, 129, 0.6)",
                        borderRadius: 4,
                    },
                    {
                        label: "Spent",
                        data: spent,
                        backgroundColor: "rgba(239, 68, 68, 0.6)",
                        borderRadius: 4,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: { grid: { display: false }, ticks: { font: { size: 10 } } },
                    y: { title: { display: true, text: "Tokens" } },
                },
                plugins: {
                    legend: { position: "top", labels: { boxWidth: 10, font: { size: 11 } } },
                },
            },
        });
    }
}

// ─── Focus Mode ──────────────────────────────────────────────────────────

function updateFocusMode(data) {
    const mode = data.mode || "off";
    const toggleBtns = document.querySelectorAll("#focus-mode-toggle .toggle-btn");
    toggleBtns.forEach(btn => {
        btn.classList.toggle("active", btn.dataset.value === mode);
    });

    const banner = document.getElementById("gaming-warning-banner");
    const warningText = document.getElementById("gaming-warning-text");
    if (data.warning && data.warning.length > 0) {
        banner.classList.remove("hidden");
        warningText.textContent = data.warning;
    } else {
        banner.classList.add("hidden");
    }
}

// ─── Settings ────────────────────────────────────────────────────────────

function loadSettings(settings) {
    if (!settings) return;

    const focusMode = settings.focus_mode || "off";
    document.querySelectorAll("#focus-mode-toggle .toggle-btn").forEach(btn => {
        btn.classList.toggle("active", btn.dataset.value === focusMode);
    });

    const dnsBlocking = settings.dns_blocking || "on";
    document.querySelectorAll("#dns-toggle .toggle-btn").forEach(btn => {
        btn.classList.toggle("active", btn.dataset.value === dnsBlocking);
    });

    const threshold = document.getElementById("auto-focus-threshold");
    if (threshold) threshold.value = settings.auto_focus_threshold_min || "30";

    const earnRate = document.getElementById("token-earn-rate");
    if (earnRate) earnRate.value = settings.token_earn_rate || "30";
    const deductRate = document.getElementById("token-deduct-rate");
    if (deductRate) deductRate.value = settings.token_deduct_rate || "15";

    const blockedApps = document.getElementById("blocked-apps-list");
    if (blockedApps) blockedApps.value = (settings.blocked_apps_custom || "").replace(/,/g, "\n");
    const whitelistedApps = document.getElementById("whitelisted-apps-list");
    if (whitelistedApps) whitelistedApps.value = (settings.whitelisted_apps || "").replace(/,/g, "\n");

    const channels = document.getElementById("whitelisted-channels");
    if (channels) channels.value = (settings.whitelisted_channels || "").replace(/,/g, "\n");
}

function renderBlockedApps(data) {
    const el = document.getElementById("blocked-apps-list");
    if (el && data.user_blacklist) {
        el.value = data.user_blacklist.join("\n");
    }
    const wl = document.getElementById("whitelisted-apps-list");
    if (wl && data.user_whitelist) {
        wl.value = data.user_whitelist.join("\n");
    }
}

// ═══════════════════════════════════════════════════════════
// Password Modal
// ═══════════════════════════════════════════════════════════

let currentModalCallback = null;
let currentModalAction = null;

function showPasswordModal(title, message, callback, action = null) {
    currentModalCallback = callback;
    currentModalAction = action;

    document.getElementById("modal-title").textContent = title;
    document.getElementById("modal-message").textContent = message;
    document.getElementById("modal-password").value = "";
    document.getElementById("modal-error").classList.add("hidden");
    document.getElementById("modal-lockout").classList.add("hidden");
    document.getElementById("modal-extra-fields").innerHTML = "";
    document.getElementById("modal-password").style.display = "";
    document.getElementById("password-modal").classList.remove("hidden");
    document.getElementById("modal-password").focus();
}

function closeModal() {
    document.getElementById("password-modal").classList.add("hidden");
    currentModalCallback = null;
    currentModalAction = null;
}

function showModalError(message) {
    const el = document.getElementById("modal-error");
    el.textContent = message;
    el.classList.remove("hidden");
    el.style.animation = "none";
    el.offsetHeight;
    el.style.animation = "shake 0.4s ease";
}

function showSecurityQuestion(question) {
    const extraFields = document.getElementById("modal-extra-fields");
    extraFields.innerHTML = `
        <p style="font-size: 0.85rem; color: var(--text-secondary); margin: 1rem 0 0.5rem;">
            Security Question: <strong>${question}</strong>
        </p>
        <input type="text" id="modal-security-answer" class="modal-input" placeholder="Your answer" style="margin-bottom: 0.5rem;">
        <input type="password" id="modal-new-password" class="modal-input" placeholder="New password (min 4 chars)">
    `;
    document.getElementById("modal-password").style.display = "none";
    document.getElementById("modal-title").textContent = "🔑 Password Recovery";
    document.getElementById("modal-message").textContent = "Answer your security question to reset your password.";
    currentModalAction = "forgot_password";
}

// ═══════════════════════════════════════════════════════════
// Toast Notifications
// ═══════════════════════════════════════════════════════════

function showToast(message, type = "info") {
    const container = document.getElementById("toast-container");
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    const icons = { success: "✅", error: "❌", info: "ℹ️" };
    toast.innerHTML = `<span>${icons[type] || ""}</span> ${message}`;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 3500);
}

// ═══════════════════════════════════════════════════════════
// Navigation
// ═══════════════════════════════════════════════════════════

function navigateTo(page) {
    document.querySelectorAll(".nav-link").forEach(link => {
        link.classList.toggle("active", link.dataset.page === page);
    });

    document.querySelectorAll(".page").forEach(p => {
        p.classList.toggle("active", p.id === `page-${page}`);
    });

    // Refresh page-specific data on navigation
    const today = new Date().toISOString().split("T")[0];
    if (page === "screentime") {
        sendWS({ action: "get_top_apps", date: today });
        sendWS({ action: "get_hourly", date: today });
    } else if (page === "webactivity") {
        sendWS({ action: "get_web_stats", date: today });
        sendWS({ action: "get_web_blocked", date: today });
        sendWS({ action: "get_recent_web" });
    } else if (page === "spotify") {
        sendWS({ action: "get_spotify" });
        sendWS({ action: "get_current_activity" });
    } else if (page === "tokens") {
        sendWS({ action: "get_tokens" });
    } else if (page === "settings") {
        sendWS({ action: "get_settings" });
        sendWS({ action: "get_blocked_apps" });
    }
}

// ═══════════════════════════════════════════════════════════
// Event Listeners
// ═══════════════════════════════════════════════════════════

document.addEventListener("DOMContentLoaded", () => {
    // Set current date
    const dateEl = document.getElementById("current-date");
    if (dateEl) {
        dateEl.textContent = new Date().toLocaleDateString("en-US", {
            weekday: "long", year: "numeric", month: "long", day: "numeric",
        });
    }

    // Navigation
    document.querySelectorAll(".nav-link").forEach(link => {
        link.addEventListener("click", (e) => {
            e.preventDefault();
            navigateTo(link.dataset.page);
        });
    });

    // Period selector (Screen Time page)
    document.querySelectorAll(".period-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            document.querySelectorAll(".period-btn").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            const period = btn.dataset.period;
            const today = new Date();
            if (period === "day") {
                sendWS({ action: "get_top_apps", date: today.toISOString().split("T")[0] });
                sendWS({ action: "get_hourly", date: today.toISOString().split("T")[0] });
            } else if (period === "month") {
                sendWS({ action: "get_monthly", year: today.getFullYear(), month: today.getMonth() + 1 });
            } else if (period === "year") {
                sendWS({ action: "get_yearly", year: today.getFullYear() });
            }
        });
    });

    // Focus mode toggle
    document.querySelectorAll("#focus-mode-toggle .toggle-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            const target = btn.dataset.value;
            if (target === "off") {
                showPasswordModal("🔐 Disable Focus Mode",
                    "Enter your admin password to turn off Focus Mode.",
                    (verified) => {
                        if (verified) {
                            sendWS({ action: "toggle_focus_mode", target: "off", password: document.getElementById("modal-password").value });
                            closeModal();
                        }
                    }
                );
            } else {
                sendWS({ action: "toggle_focus_mode", target: "on", password: "" });
            }
        });
    });

    // DNS toggle
    document.querySelectorAll("#dns-toggle .toggle-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            const enable = btn.dataset.value === "on";
            showPasswordModal("🔐 Admin Password",
                `Enter password to ${enable ? "enable" : "disable"} adult content blocking.`,
                (verified) => {
                    if (verified) {
                        sendWS({ action: "toggle_adult_block", enable, password: document.getElementById("modal-password").value });
                        closeModal();
                    }
                }
            );
        });
    });

    // Save blocked apps
    document.getElementById("btn-save-blocked-apps")?.addEventListener("click", () => {
        const apps = document.getElementById("blocked-apps-list").value
            .split("\n").map(a => a.trim()).filter(Boolean);
        showPasswordModal("🔐 Admin Password", "Enter password to update blocked apps.",
            (verified) => {
                if (verified) {
                    sendWS({ action: "update_blocked_apps", apps, password: document.getElementById("modal-password").value });
                    closeModal();
                }
            }
        );
    });

    // Save whitelisted apps
    document.getElementById("btn-save-whitelisted-apps")?.addEventListener("click", () => {
        const apps = document.getElementById("whitelisted-apps-list").value
            .split("\n").map(a => a.trim()).filter(Boolean);
        showPasswordModal("🔐 Admin Password", "Enter password to update whitelist.",
            (verified) => {
                if (verified) {
                    sendWS({ action: "update_whitelist", apps, password: document.getElementById("modal-password").value });
                    closeModal();
                }
            }
        );
    });

    // Save whitelisted channels
    document.getElementById("btn-save-channels")?.addEventListener("click", () => {
        const channels = document.getElementById("whitelisted-channels").value
            .split("\n").map(c => c.trim()).filter(Boolean).join(",");
        showPasswordModal("🔐 Admin Password", "Enter password to update YouTube whitelist.",
            (verified) => {
                if (verified) {
                    sendWS({ action: "update_settings", password: document.getElementById("modal-password").value,
                        settings: { whitelisted_channels: channels } });
                    closeModal();
                }
            }
        );
    });

    // Save token rates
    document.getElementById("btn-save-token-rates")?.addEventListener("click", () => {
        const earnRate = document.getElementById("token-earn-rate").value;
        const deductRate = document.getElementById("token-deduct-rate").value;
        const threshold = document.getElementById("auto-focus-threshold").value;
        showPasswordModal("🔐 Admin Password", "Enter password to update token rates.",
            (verified) => {
                if (verified) {
                    sendWS({ action: "update_settings", password: document.getElementById("modal-password").value,
                        settings: {
                            token_earn_rate: earnRate,
                            token_deduct_rate: deductRate,
                            auto_focus_threshold_min: threshold,
                        }
                    });
                    closeModal();
                }
            }
        );
    });

    // Change password
    document.getElementById("btn-change-password")?.addEventListener("click", () => {
        const extraFields = document.getElementById("modal-extra-fields");
        showPasswordModal("🔐 Change Password", "Enter your current password, then set a new one.", null);
        extraFields.innerHTML = `
            <input type="password" id="modal-new-password" class="modal-input" placeholder="New password (min 4 chars)" style="margin-top: 0.5rem;">
        `;
        currentModalAction = "change_password";
    });

    // Disable engine
    document.getElementById("btn-disable-engine")?.addEventListener("click", () => {
        showPasswordModal("⚡ Disable Engine",
            "This will shut down Focus Engine Pro. You'll need to restart manually.",
            (verified) => {
                if (verified) {
                    sendWS({ action: "disable_engine", password: document.getElementById("modal-password").value });
                    closeModal();
                }
            }
        );
    });

    // Spend tokens
    document.getElementById("btn-spend-tokens")?.addEventListener("click", () => {
        const extraFields = document.getElementById("modal-extra-fields");
        showPasswordModal("🪙 Spend Tokens", "Enter password and amount to spend.", null);
        extraFields.innerHTML = `
            <input type="number" id="modal-token-amount" class="modal-input" placeholder="Amount" min="1" style="margin-top: 0.5rem;">
        `;
        currentModalAction = "spend_tokens";
    });

    // Modal confirm
    document.getElementById("modal-confirm")?.addEventListener("click", () => {
        const password = document.getElementById("modal-password")?.value || "";

        if (currentModalAction === "forgot_password") {
            const answer = document.getElementById("modal-security-answer")?.value || "";
            const newPw = document.getElementById("modal-new-password")?.value || "";
            if (!answer || !newPw) {
                showModalError("Please fill in all fields.");
                return;
            }
            sendWS({ action: "forgot_password", answer, new_password: newPw });
            return;
        }

        if (currentModalAction === "change_password") {
            const newPw = document.getElementById("modal-new-password")?.value || "";
            if (newPw.length < 4) {
                showModalError("New password must be at least 4 characters.");
                return;
            }
            sendWS({ action: "change_password", old: password, new: newPw });
            return;
        }

        if (currentModalAction === "spend_tokens") {
            const amount = parseInt(document.getElementById("modal-token-amount")?.value || "0");
            if (amount <= 0) {
                showModalError("Enter a valid amount.");
                return;
            }
            sendWS({ action: "spend_tokens", password, amount });
            return;
        }

        if (!password) {
            showModalError("Please enter your password.");
            return;
        }

        if (currentModalCallback) {
            sendWS({ action: "verify_password", password });
        }
    });

    // Modal cancel / close
    document.getElementById("modal-cancel")?.addEventListener("click", closeModal);
    document.getElementById("modal-close")?.addEventListener("click", closeModal);
    document.getElementById("password-modal")?.addEventListener("click", (e) => {
        if (e.target.id === "password-modal") closeModal();
    });

    // Password visibility toggle
    document.getElementById("toggle-password-visibility")?.addEventListener("click", () => {
        const input = document.getElementById("modal-password");
        input.type = input.type === "password" ? "text" : "password";
    });

    // Forgot password link
    document.getElementById("modal-forgot-link")?.addEventListener("click", (e) => {
        e.preventDefault();
        sendWS({ action: "get_security_question" });
    });

    // Enter key in modal
    document.getElementById("modal-password")?.addEventListener("keydown", (e) => {
        if (e.key === "Enter") document.getElementById("modal-confirm")?.click();
    });

    // Connect WebSocket
    connectWebSocket();
});

// ─── Period Charts  ──────────────────────────────────────────────────────

function renderPeriodChart(data) {
    const ctx = document.getElementById("chart-top-apps");
    if (!ctx) return;

    const items = data.data || [];
    const labels = items.map(i => i.date || i.month || "");
    const categories = ["study", "gaming", "social", "entertainment", "other"];

    const datasets = categories.map(cat => ({
        label: cat.charAt(0).toUpperCase() + cat.slice(1),
        data: items.map(i => Math.round((i[cat] || 0) / 3600)),
        backgroundColor: CATEGORY_COLORS[cat]?.bg,
        borderRadius: 3,
    }));

    if (topAppsChart) {
        topAppsChart.destroy();
        topAppsChart = null;
    }

    topAppsChart = new Chart(ctx, {
        type: "bar",
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: "x",
            scales: {
                x: { stacked: true, grid: { display: false } },
                y: { stacked: true, title: { display: true, text: "Hours" } },
            },
            plugins: {
                legend: { position: "top", labels: { boxWidth: 10, font: { size: 11 } } },
            },
        },
    });
}
