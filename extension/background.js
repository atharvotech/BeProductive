/**
 * Focus Engine Pro — Chrome Extension Background Service Worker
 * 
 * Tracks time spent per domain, syncs to Python WebSocket server every 30s,
 * blocks distraction URLs (always-on + focus mode enhanced),
 * and manages focus mode state from the server.
 */

// ─── Configuration ───────────────────────────────────────────────────────

const WS_URL = "ws://localhost:8765";
const SYNC_INTERVAL_SEC = 30;
const FOCUS_CHECK_INTERVAL_SEC = 15;

// Always-blocked URL keywords (even outside focus mode)
const ALWAYS_BLOCKED_KEYWORDS = [
  "pornhub", "xvideos", "xnxx", "xhamster", "redtube",
  "youporn", "spankbang", "brazzers", "onlyfans",
  "tiktok.com", "/reels", "/shorts",
];

// Focus-mode blocked domains
const FOCUS_BLOCKED_DOMAINS = [
  "instagram.com", "facebook.com", "twitter.com", "x.com",
  "reddit.com", "snapchat.com", "pinterest.com", "tumblr.com",
  "twitch.tv", "netflix.com", "disneyplus.com", "hotstar.com",
  "primevideo.com", "hulu.com", "crunchyroll.com",
  "hbomax.com", "peacocktv.com",
  "9gag.com", "buzzfeed.com", "imgur.com",
];

// Focus-mode blocked URL keywords
const FOCUS_BLOCKED_KEYWORDS = [
  "gaming", "gameplay", "walkthrough", "let's play",
  "fortnite", "valorant", "gta", "minecraft",
  "movie", "trailer",  "memes", "funny",
  "unboxing", "haul", "vlog", "mukbang",
  "asmr",
];

// Study-safe domains (never blocked, even in focus mode)
const STUDY_SAFE_DOMAINS = [
  "stackoverflow.com", "github.com", "gitlab.com",
  "docs.python.org", "docs.microsoft.com", "learn.microsoft.com",
  "developer.mozilla.org", "w3schools.com",
  "geeksforgeeks.org", "tutorialspoint.com",
  "leetcode.com", "hackerrank.com", "codechef.com", "codeforces.com",
  "coursera.org", "udemy.com", "edx.org", "khanacademy.org",
  "codecademy.com", "freecodecamp.org",
  "npmjs.com", "pypi.org", "crates.io",
  "arxiv.org", "scholar.google.com", "wikipedia.org",
  "medium.com", "dev.to", "hashnode.dev",
  "localhost", "127.0.0.1",
  "chat.openai.com", "gemini.google.com", "claude.ai",
  "colab.research.google.com",
];

// Whitelisted YouTube channel patterns (user can add more via settings)
let whitelistedChannels = [];

// ─── State ───────────────────────────────────────────────────────────────

let timeData = {};           // { domain: { seconds: N, url: "", title: "" } }
let activeTabId = null;
let activeTabDomain = "";
let activeTabUrl = "";
let activeTabTitle = "";
let lastTickTime = Date.now();
let focusMode = false;
let wsConnection = null;
let wsConnected = false;
let reconnectTimer = null;
let reconnectDelay = 1000;

// ─── WebSocket Connection ────────────────────────────────────────────────

function connectWebSocket() {
  if (wsConnection && wsConnection.readyState === WebSocket.OPEN) return;

  try {
    wsConnection = new WebSocket(WS_URL);

    wsConnection.onopen = () => {
      console.log("[FEP] WebSocket connected");
      wsConnected = true;
      reconnectDelay = 1000;
      // Immediately check focus mode
      sendWS({ action: "get_focus_mode" });
      // Load whitelisted channels
      sendWS({ action: "get_settings" });
    };

    wsConnection.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        handleServerMessage(data);
      } catch (e) {
        console.error("[FEP] Parse error:", e);
      }
    };

    wsConnection.onclose = () => {
      wsConnected = false;
      scheduleReconnect();
    };

    wsConnection.onerror = () => {
      wsConnected = false;
    };
  } catch (e) {
    scheduleReconnect();
  }
}

function scheduleReconnect() {
  if (reconnectTimer) clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(() => {
    reconnectDelay = Math.min(reconnectDelay * 2, 30000);
    connectWebSocket();
  }, reconnectDelay);
}

function sendWS(data) {
  if (wsConnection && wsConnection.readyState === WebSocket.OPEN) {
    wsConnection.send(JSON.stringify(data));
  }
}

function handleServerMessage(data) {
  if (data.action === "focus_mode") {
    const newMode = data.mode === "on";
    if (newMode !== focusMode) {
      focusMode = newMode;
      chrome.storage.local.set({ focusMode });
      console.log(`[FEP] Focus mode: ${focusMode ? "ON" : "OFF"}`);
    }
  } else if (data.action === "focus_mode_changed") {
    focusMode = data.mode === "on";
    chrome.storage.local.set({ focusMode });
  } else if (data.action === "settings") {
    const channels = data.data?.whitelisted_channels || "";
    whitelistedChannels = channels.split(",").map(c => c.trim().toLowerCase()).filter(Boolean);
  }
}

// ─── Time Tracking ───────────────────────────────────────────────────────

function getDomain(url) {
  try {
    const u = new URL(url);
    return u.hostname.replace("www.", "");
  } catch {
    return "";
  }
}

function tickTime() {
  const now = Date.now();
  const elapsed = Math.round((now - lastTickTime) / 1000);
  lastTickTime = now;

  if (activeTabDomain && elapsed > 0 && elapsed < 300) {
    if (!timeData[activeTabDomain]) {
      timeData[activeTabDomain] = { seconds: 0, url: "", title: "" };
    }
    timeData[activeTabDomain].seconds += elapsed;
    timeData[activeTabDomain].url = activeTabUrl;
    timeData[activeTabDomain].title = activeTabTitle;
  }
}

function updateActiveTab() {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (tabs && tabs[0]) {
      const tab = tabs[0];
      activeTabId = tab.id;
      activeTabUrl = tab.url || "";
      activeTabTitle = tab.title || "";
      activeTabDomain = getDomain(activeTabUrl);
    }
  });
}

// ─── Sync to Server ──────────────────────────────────────────────────────

function syncTimeData() {
  tickTime(); // Final tick before sync

  for (const [domain, data] of Object.entries(timeData)) {
    if (data.seconds > 0) {
      const category = classifyDomain(domain, data.title);
      sendWS({
        action: "log_web_time",
        domain: domain,
        url: data.url,
        title: data.title,
        seconds: data.seconds,
        category: category,
      });
    }
  }
  timeData = {};
}

function classifyDomain(domain, title = "") {
  const d = domain.toLowerCase();
  const t = title.toLowerCase();

  // Study sites
  if (STUDY_SAFE_DOMAINS.some(sd => d.includes(sd))) return "study";

  // Social media
  if (FOCUS_BLOCKED_DOMAINS.some(bd => d.includes(bd) && 
      ["instagram", "facebook", "twitter", "x.com", "reddit", "snapchat", "pinterest", "tumblr"]
        .some(s => bd.includes(s)))) return "social";

  // Entertainment
  if (FOCUS_BLOCKED_DOMAINS.some(bd => d.includes(bd))) return "entertainment";

  // YouTube — classify by title
  if (d.includes("youtube.com")) {
    if (STUDY_SAFE_KEYWORDS_IN_TITLE(t)) return "study";
    if (FOCUS_BLOCKED_KEYWORDS.some(kw => t.includes(kw))) return "entertainment";
    return "entertainment"; // Default YouTube = entertainment
  }

  // Gaming
  if (FOCUS_BLOCKED_KEYWORDS.some(kw => t.includes(kw) || d.includes(kw))) return "gaming";

  return "other";
}

function STUDY_SAFE_KEYWORDS_IN_TITLE(title) {
  const keywords = [
    "tutorial", "course", "lecture", "lesson", "programming",
    "coding", "python", "javascript", "html", "css", "react",
    "node", "algorithm", "data structure", "math", "physics",
    "chemistry", "biology", "history", "geography", "english",
    "science", "engineering", "how to code", "learn",
    "documentation", "explained", "education",
  ];
  return keywords.some(kw => title.includes(kw));
}

// ─── URL Blocking ────────────────────────────────────────────────────────

function shouldBlockUrl(url, title = "") {
  if (!url || url.startsWith("chrome://") || url.startsWith("chrome-extension://")) {
    return { block: false, reason: "" };
  }

  const urlLower = url.toLowerCase();
  const domain = getDomain(url);
  const titleLower = (title || "").toLowerCase();

  // Always blocked (adult content, tiktok, reels, shorts)
  for (const kw of ALWAYS_BLOCKED_KEYWORDS) {
    if (urlLower.includes(kw)) {
      return { block: true, reason: `Blocked keyword: ${kw}` };
    }
  }

  // Focus mode blocking
  if (focusMode) {
    // Check if study-safe
    if (STUDY_SAFE_DOMAINS.some(sd => domain.includes(sd))) {
      return { block: false, reason: "" };
    }

    // YouTube special handling
    if (domain.includes("youtube.com")) {
      // Allow whitelisted channels
      if (whitelistedChannels.length > 0) {
        const isWhitelisted = whitelistedChannels.some(ch => 
          urlLower.includes(ch) || titleLower.includes(ch)
        );
        if (isWhitelisted) return { block: false, reason: "" };
      }
      // Allow study content by title
      if (STUDY_SAFE_KEYWORDS_IN_TITLE(titleLower)) {
        return { block: false, reason: "" };
      }
      // Block non-study YouTube in focus mode
      return { block: true, reason: "YouTube non-study content blocked in Focus Mode" };
    }

    // Block social/entertainment domains
    for (const bd of FOCUS_BLOCKED_DOMAINS) {
      if (domain.includes(bd)) {
        return { block: true, reason: `${bd} blocked in Focus Mode` };
      }
    }

    // Block by title keywords
    for (const kw of FOCUS_BLOCKED_KEYWORDS) {
      if (titleLower.includes(kw) || urlLower.includes(kw)) {
        return { block: true, reason: `Content keyword "${kw}" blocked in Focus Mode` };
      }
    }
  }

  return { block: false, reason: "" };
}

// ─── Navigation Blocking ─────────────────────────────────────────────────

chrome.webNavigation.onBeforeNavigate.addListener((details) => {
  if (details.frameId !== 0) return; // Only main frame

  const { block, reason } = shouldBlockUrl(details.url);
  if (block) {
    // Redirect to blocked page
    const blockedHtml = `data:text/html,${encodeURIComponent(getBlockedPageHTML(reason))}`;
    chrome.tabs.update(details.tabId, { url: blockedHtml });

    // Log the blocked attempt
    const domain = getDomain(details.url);
    sendWS({
      action: "log_web_time",
      domain: domain,
      url: details.url,
      title: reason,
      seconds: 0,
      category: "blocked",
    });
  }
});

// Also check on tab updates (for SPAs that change title without navigation)
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.title || changeInfo.url) {
    const url = tab.url || "";
    const title = tab.title || "";
    const { block, reason } = shouldBlockUrl(url, title);
    if (block && !url.startsWith("data:")) {
      const blockedHtml = `data:text/html,${encodeURIComponent(getBlockedPageHTML(reason))}`;
      chrome.tabs.update(tabId, { url: blockedHtml });
    }
  }
});

function getBlockedPageHTML(reason) {
  return `
<!DOCTYPE html>
<html>
<head>
  <title>🚫 Blocked — Focus Engine Pro</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      background: linear-gradient(135deg, #0a0e27 0%, #1a1040 50%, #0a0e27 100%);
      color: #fff;
      font-family: 'Segoe UI', Inter, sans-serif;
      text-align: center;
      padding: 2rem;
    }
    .container {
      max-width: 500px;
      background: rgba(255,255,255,0.05);
      backdrop-filter: blur(20px);
      border: 1px solid rgba(255,255,255,0.1);
      border-radius: 24px;
      padding: 3rem 2rem;
    }
    .icon { font-size: 4rem; margin-bottom: 1rem; }
    h1 { font-size: 1.8rem; margin-bottom: 0.5rem; color: #f87171; }
    p { color: rgba(255,255,255,0.7); margin-bottom: 1.5rem; line-height: 1.6; }
    .reason {
      background: rgba(248,113,113,0.15);
      border: 1px solid rgba(248,113,113,0.3);
      border-radius: 12px;
      padding: 0.75rem 1rem;
      font-size: 0.85rem;
      color: #fca5a5;
      margin-bottom: 1.5rem;
    }
    .quote {
      font-style: italic;
      color: rgba(255,255,255,0.5);
      font-size: 0.9rem;
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="icon">🚫</div>
    <h1>Get Back to Work!</h1>
    <p>This page has been blocked by Focus Engine Pro.</p>
    <div class="reason">${reason}</div>
    <p class="quote">"The secret of getting ahead is getting started." — Mark Twain</p>
  </div>
</body>
</html>`;
}

// ─── Tab & Window Events ─────────────────────────────────────────────────

chrome.tabs.onActivated.addListener((activeInfo) => {
  tickTime();
  updateActiveTab();
});

chrome.windows.onFocusChanged.addListener((windowId) => {
  tickTime();
  if (windowId === chrome.windows.WINDOW_ID_NONE) {
    activeTabDomain = "";
  } else {
    updateActiveTab();
  }
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (tabId === activeTabId && (changeInfo.url || changeInfo.title)) {
    tickTime();
    activeTabUrl = tab.url || activeTabUrl;
    activeTabTitle = tab.title || activeTabTitle;
    activeTabDomain = getDomain(activeTabUrl);
  }
});

// ─── Content Script Message Handler ──────────────────────────────────────

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "page_metadata") {
    const url = sender.tab?.url || "";
    const title = message.title || "";
    const { block, reason } = shouldBlockUrl(url, title);
    
    if (block) {
      // Tell content script to show overlay
      sendResponse({ action: "block", reason: reason });
    } else {
      sendResponse({ action: "allow" });
    }
  }
  return true; // Keep channel open for async response
});

// ─── Alarms (periodic tasks) ─────────────────────────────────────────────

chrome.alarms.create("syncTime", { periodInMinutes: SYNC_INTERVAL_SEC / 60 });
chrome.alarms.create("checkFocus", { periodInMinutes: FOCUS_CHECK_INTERVAL_SEC / 60 });
chrome.alarms.create("tickTime", { periodInMinutes: 0.05 }); // Every 3 seconds

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "syncTime") {
    syncTimeData();
  } else if (alarm.name === "checkFocus") {
    sendWS({ action: "get_focus_mode" });
  } else if (alarm.name === "tickTime") {
    tickTime();
    updateActiveTab();
  }
});

// ─── Initialize ──────────────────────────────────────────────────────────

// Load stored focus mode state
chrome.storage.local.get(["focusMode"], (result) => {
  focusMode = result.focusMode || false;
});

// Connect to server
connectWebSocket();

// Initial tab check
updateActiveTab();

console.log("[FEP] Focus Engine Pro extension loaded");
