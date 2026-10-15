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

// Theme Toggle (Defaults to Clean Light Theme)
const themeToggleBtn = document.getElementById("themeToggleBtn");
const themeToggleIcon = document.getElementById("themeToggleIcon");
const themeToggleText = document.getElementById("themeToggleText");

function setTheme(theme) {
  if (theme === "dark") {
    document.documentElement.setAttribute("data-theme", "dark");
    if (themeToggleIcon) themeToggleIcon.textContent = "🌙";
    if (themeToggleText) themeToggleText.textContent = "Dark";
    localStorage.setItem("scamshield_theme", "dark");
  } else {
    document.documentElement.removeAttribute("data-theme");
    if (themeToggleIcon) themeToggleIcon.textContent = "☀️";
    if (themeToggleText) themeToggleText.textContent = "Light";
    localStorage.setItem("scamshield_theme", "light");
  }
}

// Restore theme (defaults to light)
const savedTheme = localStorage.getItem("scamshield_theme") || "light";
setTheme(savedTheme);

if (themeToggleBtn) {
  themeToggleBtn.addEventListener("click", () => {
    const isDark = document.documentElement.getAttribute("data-theme") === "dark";
    setTheme(isDark ? "light" : "dark");
  });
}

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
    statusPulse.style.background = "var(--accent-green)";
    statusPulse.style.boxShadow = "none";
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
    statusPulse.style.background = "var(--accent-red)";
    statusPulse.style.boxShadow = "none";
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

// ── Live Model Training Studio ───────────────────────────────────────────────

const btnOpenTrainer = document.getElementById("btnOpenTrainer");
const btnCloseTrainer = document.getElementById("btnCloseTrainer");
const trainerModal = document.getElementById("trainerModal");
const btnStartTraining = document.getElementById("btnStartTraining");
const modelSelectTrainer = document.getElementById("modelSelectTrainer");
const trainingStatusLabel = document.getElementById("trainingStatusLabel");
const trainingPercentLabel = document.getElementById("trainingPercentLabel");
const trainingProgressBar = document.getElementById("trainingProgressBar");
const trainingResultsBox = document.getElementById("trainingResultsBox");

let trainSocket = null;

if (btnOpenTrainer && trainerModal) {
  btnOpenTrainer.addEventListener("click", () => {
    trainerModal.style.display = "flex";
  });
}

if (btnCloseTrainer && trainerModal) {
  btnCloseTrainer.addEventListener("click", () => {
    trainerModal.style.display = "none";
  });
}

if (trainerModal) {
  trainerModal.addEventListener("click", (e) => {
    if (e.target === trainerModal) {
      trainerModal.style.display = "none";
    }
  });
}

if (btnStartTraining) {
  btnStartTraining.addEventListener("click", () => {
    btnStartTraining.disabled = true;
    btnStartTraining.textContent = "⏳ Training...";
    trainingStatusLabel.textContent = "Initializing connection to training engine...";
    trainingPercentLabel.textContent = "0%";
    trainingProgressBar.style.width = "0%";
    trainingResultsBox.style.display = "none";

    // Reset step styles
    for (let i = 1; i <= 4; i++) {
      const stepEl = document.getElementById(`step${i}`);
      const badgeEl = document.getElementById(`stepBadge${i}`);
      if (stepEl) stepEl.className = "step-item";
      if (badgeEl) {
        badgeEl.className = "badge-pill";
        badgeEl.textContent = "Waiting";
      }
    }

    const trainWsUrl = `ws://${WS_HOST}:${WS_PORT}/ws/train`;
    trainSocket = new WebSocket(trainWsUrl);

    trainSocket.onopen = () => {
      trainSocket.send(JSON.stringify({
        type: "START_TRAINING",
        pipeline: modelSelectTrainer ? modelSelectTrainer.value : "both"
      }));
    };

    trainSocket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        const percent = data.percent || 0;
        trainingProgressBar.style.width = `${percent}%`;
        trainingPercentLabel.textContent = `${percent}%`;
        trainingStatusLabel.textContent = data.status || "";

        // Activate step item
        if (data.step >= 1 && data.step <= 4) {
          for (let i = 1; i < data.step; i++) {
            const prevStep = document.getElementById(`step${i}`);
            const prevBadge = document.getElementById(`stepBadge${i}`);
            if (prevStep) prevStep.className = "step-item done";
            if (prevBadge) {
              prevBadge.className = "badge-pill";
              prevBadge.style.color = "var(--accent-green)";
              prevBadge.textContent = "Done";
            }
          }
          const curStep = document.getElementById(`step${data.step}`);
          const curBadge = document.getElementById(`stepBadge${data.step}`);
          if (curStep) curStep.className = "step-item active";
          if (curBadge) {
            curBadge.className = "badge-pill active";
            curBadge.textContent = "Running";
          }
        }

        if (data.step === 5 && data.metrics) {
          for (let i = 1; i <= 4; i++) {
            const stepEl = document.getElementById(`step${i}`);
            const badgeEl = document.getElementById(`stepBadge${i}`);
            if (stepEl) stepEl.className = "step-item done";
            if (badgeEl) {
              badgeEl.className = "badge-pill";
              badgeEl.style.color = "var(--accent-green)";
              badgeEl.textContent = "Done";
            }
          }
          trainingResultsBox.style.display = "block";
          document.getElementById("resF1").textContent = data.metrics.f1;
          document.getElementById("resPrAuc").textContent = data.metrics.pr_auc;
          document.getElementById("resTau").textContent = data.metrics.tau;
          document.getElementById("resFpr").textContent = data.metrics.fpr;

          btnStartTraining.disabled = false;
          btnStartTraining.textContent = "▶ Retrain Model Live";
        }
      } catch (err) {
        console.error("Training WS parse error:", err);
      }
    };

    trainSocket.onerror = (err) => {
      console.error("Training WS error:", err);
      trainingStatusLabel.textContent = "Training engine error. Reconnecting...";
      btnStartTraining.disabled = false;
      btnStartTraining.textContent = "▶ Train Model Live";
    };
  });
}

connectWS();
