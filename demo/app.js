/**
 * demo/app.js
 *
 * Client application for Scam Shield Replay Inspector.
 * Manages WebSocket communication with demo/replay_server.py,
 * updates real-time metrics strip, live chat feed, cluster graph,
 * and handles side-by-side comparison (Full System vs Text-Only).
 */

const WS_PORT = window.location.port ? window.location.port : "8001";
const WS_HOST = window.location.hostname ? window.location.hostname : "127.0.0.1";
const WS_URL = `ws://${WS_HOST}:${WS_PORT}/ws/demo`;

let socket = null;
let isPlaying = false;
let selectedMessageData = null;

// DOM Elements
const statusPulse = document.getElementById("statusPulse");
const statusLabel = document.getElementById("statusLabel");
const stealthSelect = document.getElementById("stealthSelect");
const speedSelect = document.getElementById("speedSelect");
const focusedDemoToggle = document.getElementById("focusedDemoToggle");
const sideBySideToggle = document.getElementById("sideBySideToggle");
const btnPlay = document.getElementById("btnPlay");
const btnPause = document.getElementById("btnPause");
const btnReset = document.getElementById("btnReset");

// Restore saved preferences across reloads
if (localStorage.getItem("scamshield_stealth")) {
  stealthSelect.value = localStorage.getItem("scamshield_stealth");
}
if (localStorage.getItem("scamshield_speed")) {
  speedSelect.value = localStorage.getItem("scamshield_speed");
}
if (localStorage.getItem("scamshield_focused") !== null && focusedDemoToggle) {
  focusedDemoToggle.checked = (localStorage.getItem("scamshield_focused") === "true");
}

// Metrics
const valScanned = document.getElementById("valScanned");
const valAttacksTotal = document.getElementById("valAttacksTotal");
const valRecallB4 = document.getElementById("valRecallB4");
const subRecallB4 = document.getElementById("subRecallB4");
const valRecallB2 = document.getElementById("valRecallB2");
const subRecallB2 = document.getElementById("subRecallB2");
const valPrecB4 = document.getElementById("valPrecB4");
const valFprB4 = document.getElementById("valFprB4");
const valAbstained = document.getElementById("valAbstained");

// Chat & Sidebar
const chatFeed = document.getElementById("chatFeed");
const placeholderFeed = document.getElementById("placeholderFeed");
const clusterStatusBadge = document.getElementById("clusterStatusBadge");
const clusterAccountsCount = document.getElementById("clusterAccountsCount");
const clusterCohesionVal = document.getElementById("clusterCohesionVal");
const meterCohesion = document.getElementById("meterCohesion");
const clusterSynchronyVal = document.getElementById("clusterSynchronyVal");
const meterSynchrony = document.getElementById("meterSynchrony");
const clusterAccountsList = document.getElementById("clusterAccountsList");
const evidenceBody = document.getElementById("evidenceBody");

function connectWS() {
  socket = new WebSocket(WS_URL);

  socket.onopen = () => {
    statusPulse.style.background = "#10b981";
    statusPulse.style.boxShadow = "0 0 8px #10b981";
    statusLabel.textContent = "Connected to Replay Server";
  };

  socket.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === "MESSAGE_SCORED") {
        handleScoredMessage(data);
      } else if (data.type === "STREAM_FINISHED") {
        statusLabel.textContent = "Replay Stream Completed";
        btnPlay.textContent = "▶ Start Replay";
        isPlaying = false;
      }
    } catch (e) {
      console.error("Message parse error:", e);
    }
  };

  socket.onclose = () => {
    statusPulse.style.background = "#ef4444";
    statusPulse.style.boxShadow = "0 0 8px #ef4444";
    statusLabel.textContent = "Disconnected — Reconnecting...";
    setTimeout(connectWS, 2000);
  };
}

function handleScoredMessage(data) {
  if (placeholderFeed) {
    placeholderFeed.style.display = "none";
  }

  const msg = data.message;
  const b4 = data.b4;
  const b2 = data.b2;
  const stats = data.stats;
  const cluster = data.cluster_meta;

  // 1. Update Metrics Strip
  valScanned.textContent = stats.scanned;
  valAttacksTotal.textContent = stats.attacks_total;
  valRecallB4.textContent = `${(stats.recall_b4 * 100).toFixed(1)}%`;
  subRecallB4.textContent = `B4: ${stats.recall_b4 >= 0.8 ? "Robust Detection" : "Degrading"}`;
  valRecallB2.textContent = `${(stats.recall_b2 * 100).toFixed(1)}%`;
  subRecallB2.textContent = b2.is_flagged ? "Flagged Text" : "Missed (Semantic Camouflage)";
  valPrecB4.textContent = `${(stats.prec_b4 * 100).toFixed(1)}%`;
  valFprB4.textContent = `FPR on Genuine: ${(stats.fp_b4 / Math.max(stats.scanned - stats.attacks_total, 1) * 100).toFixed(1)}%`;
  valAbstained.textContent = stats.abstained;

  // 2. Append Chat Row
  const isAttack = (msg.ground_truth === "attack" || msg.ground_truth === "scam_campaign");
  const row = document.createElement("div");
  row.className = `chat-row ${isAttack ? "is-attack" : ""}`;

  let verdictClass = "verdict-clear";
  let verdictIcon = "✅";
  if (b4.unverifiable) {
    verdictClass = "verdict-unverifiable";
    verdictIcon = "❓";
  } else if (b4.verdict === "likely_campaign") {
    verdictClass = "verdict-campaign";
    verdictIcon = "🚫";
  } else if (b4.verdict === "suspicious") {
    verdictClass = "verdict-suspicious";
    verdictIcon = "⚡";
  }

  const showSideBySide = sideBySideToggle.checked;
  let b2PillHtml = "";
  if (showSideBySide) {
    if (isAttack) {
      if (b2.is_flagged) {
        b2PillHtml = `<span class="side-by-side-comparison">
          <span class="b2-pill b2-caught">✅ B2 Caught (Flagged)</span>
        </span>`;
      } else {
        b2PillHtml = `<span class="side-by-side-comparison">
          <span class="b2-pill b2-missed">❌ Missed by B2 (Clear)</span>
        </span>`;
      }
    } else {
      if (b2.is_flagged) {
        b2PillHtml = `<span class="side-by-side-comparison">
          <span class="b2-pill b2-false-alarm">⚠️ B2 False Alarm</span>
        </span>`;
      } else {
        b2PillHtml = `<span class="side-by-side-comparison">
          <span class="b2-pill b2-neutral">Text-Only: Clear</span>
        </span>`;
      }
    }
  }

  row.innerHTML = `
    <div class="chat-meta">
      <span class="author-pill">${msg.author}</span>
      <span class="timestamp-text">${new Date(msg.timestamp).toLocaleTimeString()}</span>
      <span class="gt-badge ${isAttack ? "gt-attack" : "gt-genuine"}">
        ${isAttack ? `ATTACK (${msg.stealth_level})` : "GENUINE"}
      </span>
    </div>
    <div class="chat-text">${escapeHtml(msg.text)}</div>
    <div class="chat-verdicts">
      <span class="verdict-tag ${verdictClass}">
        <span>${verdictIcon}</span>
        <span>${b4.unverifiable ? "Unverifiable" : b4.verdict_label} (${(b4.trust_score * 100).toFixed(0)}%)</span>
      </span>
      ${b2PillHtml}
    </div>
  `;

  row.addEventListener("click", () => {
    document.querySelectorAll(".chat-row").forEach(r => r.classList.remove("is-selected"));
    row.classList.add("is-selected");
    renderEvidence(data);
  });

  chatFeed.appendChild(row);
  chatFeed.scrollTop = chatFeed.scrollHeight;

  // 3. Update Cluster Panel
  if (cluster && cluster.is_cluster) {
    clusterStatusBadge.className = "badge-pill active";
    clusterStatusBadge.textContent = "Bot Ring Cluster Active";
    clusterAccountsCount.textContent = `${cluster.cluster_accounts.length} accounts`;
    clusterCohesionVal.textContent = b4.features.cluster_cohesion.toFixed(2);
    meterCohesion.style.width = `${Math.min(100, b4.features.cluster_cohesion * 100)}%`;
    clusterSynchronyVal.textContent = `${b4.features.rate_synchrony.toFixed(2)}x`;
    meterSynchrony.style.width = `${Math.min(100, b4.features.rate_synchrony * 50)}%`;

    clusterAccountsList.innerHTML = cluster.cluster_accounts
      .map(acc => `<span class="account-chip">${acc}</span>`)
      .join("");
  }
}

function renderEvidence(data) {
  const b4 = data.b4;
  const reasons = b4.reasons || [];

  const reasonsHtml = reasons.length > 0
    ? reasons.map(r => `
        <div class="evidence-item ${r.type}">
          <span>${r.type === "positive" ? "✅" : "🚩"}</span>
          <span>${escapeHtml(r.text)}</span>
        </div>
      `).join("")
    : `<div class="evidence-item positive"><span>ℹ️</span><span>No coordination or scam flags detected.</span></div>`;

  evidenceBody.innerHTML = `
    <div class="cluster-metric-row" style="margin-bottom: 8px;">
      <span class="label">Campaign Probability:</span>
      <span class="val font-mono">${((1.0 - b4.trust_score) * 100).toFixed(1)}%</span>
    </div>
    <div class="cluster-metric-row" style="margin-bottom: 12px;">
      <span class="label">Abstention Status:</span>
      <span class="val font-mono">${b4.unverifiable ? "Unverifiable" : "Committed"}</span>
    </div>
    <div class="evidence-list">${reasonsHtml}</div>
  `;
}

function escapeHtml(str) {
  return (str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function resetFeedAndMetrics() {
  chatFeed.innerHTML = "";
  if (placeholderFeed) {
    placeholderFeed.style.display = "block";
    chatFeed.appendChild(placeholderFeed);
  }
  clusterStatusBadge.className = "badge-pill";
  clusterStatusBadge.textContent = "No Active Cluster";
  clusterAccountsCount.textContent = "0 accounts";
  clusterAccountsList.innerHTML = '<span class="empty-hint">Waiting for coordinated clusters...</span>';
  evidenceBody.innerHTML = '<p class="empty-hint">Click on any message in the chat to inspect its exact evidence.</p>';
  valScanned.textContent = "0";
  valAttacksTotal.textContent = "0";
  valRecallB4.textContent = "0.0%";
  subRecallB4.textContent = "0 / 0 detected";
  valRecallB2.textContent = "0.0%";
  subRecallB2.textContent = "Fails at L2+ Paraphrases";
  valPrecB4.textContent = "100.0%";
  valFprB4.textContent = "FPR on Genuine: 0.0%";
  valAbstained.textContent = "0";
}

// ── Control Listeners ─────────────────────────────────────────────────────────

btnPlay.addEventListener("click", () => {
  if (!socket || socket.readyState !== WebSocket.OPEN) return;
  isPlaying = true;
  btnPlay.textContent = "▶ Replaying...";
  statusLabel.textContent = `Streaming Level ${stealthSelect.value}...`;
  resetFeedAndMetrics();
  socket.send(JSON.stringify({
    type: "START",
    speed: parseFloat(speedSelect.value),
    stealth_level: stealthSelect.value,
    side_by_side: sideBySideToggle.checked,
    focused_demo: focusedDemoToggle ? focusedDemoToggle.checked : true,
  }));
});

btnPause.addEventListener("click", () => {
  if (!socket || socket.readyState !== WebSocket.OPEN) return;
  isPlaying = false;
  btnPlay.textContent = "▶ Resume";
  statusLabel.textContent = "Replay Paused";
  socket.send(JSON.stringify({ type: "PAUSE" }));
});

btnReset.addEventListener("click", () => {
  resetFeedAndMetrics();
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ type: "PAUSE" }));
  }
  btnPlay.textContent = "▶ Start Replay";
  isPlaying = false;
  statusLabel.textContent = "Connected to Replay Server";
});

stealthSelect.addEventListener("change", () => {
  localStorage.setItem("scamshield_stealth", stealthSelect.value);
  resetFeedAndMetrics();
  if (socket && socket.readyState === WebSocket.OPEN) {
    isPlaying = true;
    btnPlay.textContent = "▶ Replaying...";
    statusLabel.textContent = `Streaming Level ${stealthSelect.value}...`;
    socket.send(JSON.stringify({
      type: "SET_LEVEL",
      stealth_level: stealthSelect.value,
      focused_demo: focusedDemoToggle ? focusedDemoToggle.checked : true,
    }));
  }
});

speedSelect.addEventListener("change", () => {
  localStorage.setItem("scamshield_speed", speedSelect.value);
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ type: "SET_SPEED", speed: parseFloat(speedSelect.value) }));
  }
});

if (focusedDemoToggle) {
  focusedDemoToggle.addEventListener("change", () => {
    localStorage.setItem("scamshield_focused", focusedDemoToggle.checked);
    resetFeedAndMetrics();
    if (socket && socket.readyState === WebSocket.OPEN) {
      isPlaying = true;
      btnPlay.textContent = "▶ Replaying...";
      statusLabel.textContent = `Streaming Level ${stealthSelect.value}...`;
      socket.send(JSON.stringify({
        type: "START",
        speed: parseFloat(speedSelect.value),
        stealth_level: stealthSelect.value,
        side_by_side: sideBySideToggle.checked,
        focused_demo: focusedDemoToggle.checked,
      }));
    }
  });
}

connectWS();
