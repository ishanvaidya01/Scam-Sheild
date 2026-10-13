/**
 * background.js  (v2)
 *
 * Service worker for the Scam Shield extension.
 * Manages the single WebSocket connection to the ML backend,
 * fans out scored results to all content script ports,
 * and forwards feedback submissions to the /feedback REST endpoint.
 */

// Backend host is configurable via chrome.storage.local key "backendHost".
// Default: 127.0.0.1:8000 (local development).
// To change: chrome.storage.local.set({ backendHost: "192.168.1.10:8000" })
const DEFAULT_HOST = "127.0.0.1:8000";

let WS_URL = `ws://${DEFAULT_HOST}/ws`;
let FEEDBACK_URL = `http://${DEFAULT_HOST}/feedback`;

// Load persisted host on startup
chrome.storage.local.get(["backendHost", "sensitivity"], (result) => {
  if (result.backendHost) {
    WS_URL = `ws://${result.backendHost}/ws`;
    FEEDBACK_URL = `http://${result.backendHost}/feedback`;
  }
  if (result.sensitivity) {
    currentSensitivity = result.sensitivity;
  }
  connectWebSocket();
});

let socket = null;
let reconnectInterval = 2000;
let connectedPorts = new Set();
let messageQueue = [];
let currentSensitivity = 3;  // default

// ── WebSocket management ───────────────────────────────────────────────────────
function connectWebSocket() {
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
    return;
  }

  console.log("[ScamShield BG] Connecting to ML backend...");
  socket = new WebSocket(WS_URL);

  socket.onopen = () => {
    console.log("[ScamShield BG] Connected to ML backend v2.0");
    // Flush queued messages
    while (messageQueue.length > 0 && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(messageQueue.shift()));
    }
    // Sync sensitivity with backend
    socket.send(JSON.stringify({ type: "SET_SENSITIVITY", value: currentSensitivity }));
  };

  socket.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);

      // Control ACKs — don't fan out to content scripts
      if (data.type === "SENSITIVITY_ACK" || data.type === "STATS") {
        // Broadcast control messages to all ports (popup may be listening)
        connectedPorts.forEach((port) => {
          try { port.postMessage({ type: data.type, data }); } catch (_) {}
        });
        return;
      }

      // Score results → fan out to all active content script ports
      connectedPorts.forEach((port) => {
        try {
          port.postMessage({ type: "SCORE_RESULT", data });
        } catch (err) {
          connectedPorts.delete(port);
        }
      });
    } catch (e) {
      console.error("[ScamShield BG] Failed to parse WS message:", e);
    }
  };

  socket.onclose = () => {
    console.log("[ScamShield BG] WS closed. Reconnecting...");
    socket = null;
    setTimeout(connectWebSocket, reconnectInterval);
  };

  socket.onerror = (err) => {
    console.error("[ScamShield BG] WS error:", err);
  };
}

// ── Port listener (from content scripts and popup) ─────────────────────────────
chrome.runtime.onConnect.addListener((port) => {
  if (port.name === "chat-stream" || port.name === "popup-stream") {
    connectedPorts.add(port);

    port.onMessage.addListener((message) => {
      // ── New comment from content script ───────────────────────────────
      if (message.type === "NEW_COMMENT") {
        const payload = message.data;
        if (socket && socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify(payload));
        } else {
          messageQueue.push(payload);
          if (!socket || socket.readyState === WebSocket.CLOSED) {
            connectWebSocket();
          }
        }
      }

      // ── Sensitivity change from popup ─────────────────────────────────
      if (message.type === "SET_SENSITIVITY") {
        currentSensitivity = message.value;
        if (socket && socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ type: "SET_SENSITIVITY", value: currentSensitivity }));
        }
        // Save to storage for persistence
        chrome.storage.local.set({ sensitivity: currentSensitivity });
      }

      // ── Stats request from popup ──────────────────────────────────────
      if (message.type === "GET_STATS") {
        if (socket && socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ type: "GET_STATS" }));
        }
      }

      // ── Feedback from content script ──────────────────────────────────
      if (message.type === "FEEDBACK") {
        submitFeedback(message.data);
      }
    });

    port.onDisconnect.addListener(() => {
      connectedPorts.delete(port);
    });
  }
});

// ── Feedback submission (REST) ────────────────────────────────────────────────
async function submitFeedback(feedbackData) {
  try {
    await fetch(FEEDBACK_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(feedbackData),
    });
    console.log("[ScamShield BG] Feedback submitted:", feedbackData.comment_id);
  } catch (e) {
    console.warn("[ScamShield BG] Feedback submission failed:", e);
  }
}

// ── Shield state broadcast ────────────────────────────────────────────────────
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "SET_SHIELD_STATE") {
    // Broadcast to all tabs
    chrome.tabs.query({ url: "*://www.youtube.com/*" }, (tabs) => {
      tabs.forEach((tab) => {
        chrome.tabs.sendMessage(tab.id, msg).catch(() => {});
      });
    });
  }
});
