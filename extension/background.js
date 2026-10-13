/**
 * background.js
 *
 * Service worker for the Scam Shield extension.
 * Manages the WebSocket connection to the ML backend
 * and fans out scored results to all content script ports.
 */

const DEFAULT_HOST = "127.0.0.1:8000";
let WS_URL = `ws://${DEFAULT_HOST}/ws`;

chrome.storage.local.get(["backendHost"], (result) => {
  if (result.backendHost) {
    WS_URL = `ws://${result.backendHost}/ws`;
  }
  connectWebSocket();
});

let socket = null;
let reconnectInterval = 2000;
let connectedPorts = new Set();
let messageQueue = [];

function connectWebSocket() {
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
    return;
  }

  console.log("[ScamShield BG] Connecting to ML backend...");
  socket = new WebSocket(WS_URL);

  socket.onopen = () => {
    console.log("[ScamShield BG] Connected to ML backend");
    while (messageQueue.length > 0 && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(messageQueue.shift()));
    }
  };

  socket.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);

      if (data.type === "STATS") {
        connectedPorts.forEach((port) => {
          try { port.postMessage({ type: data.type, data }); } catch (_) {}
        });
        return;
      }

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

chrome.runtime.onConnect.addListener((port) => {
  if (port.name === "chat-stream" || port.name === "popup-stream") {
    connectedPorts.add(port);

    port.onMessage.addListener((message) => {
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

      if (message.type === "GET_STATS") {
        if (socket && socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ type: "GET_STATS" }));
        }
      }
    });

    port.onDisconnect.addListener(() => {
      connectedPorts.delete(port);
    });
  }
});

chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === "SET_SHIELD_STATE") {
    chrome.tabs.query({ url: "*://www.youtube.com/*" }, (tabs) => {
      tabs.forEach((tab) => {
        chrome.tabs.sendMessage(tab.id, msg).catch(() => {});
      });
    });
  }
});
