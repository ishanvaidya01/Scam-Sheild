const SENS_TEXT = {
  1: "Lenient — only flags coordinated bot rings.",
  2: "Conservative — flags strong scam signals only.",
  3: "Balanced — flags clear threats only.",
  4: "Aggressive — flags moderate suspicious patterns.",
  5: "Strict — maximum sensitivity, higher false positive rate.",
};

document.addEventListener("DOMContentLoaded", () => {
  const toggle      = document.getElementById("toggleShield");
  const statusDot   = document.getElementById("statusDot");
  const statusText  = document.getElementById("statusText");
  const headerGlow  = document.getElementById("headerGlow");
  const slider      = document.getElementById("sensitivitySlider");
  const sensDesc    = document.getElementById("sensDesc");
  const statScanned = document.getElementById("statScanned");
  const statFlagged = document.getElementById("statFlagged");
  const statScam    = document.getElementById("statScam");

  let bgPort = null;
  try {
    bgPort = chrome.runtime.connect({ name: "popup-stream" });
    bgPort.onMessage.addListener(handleBgMsg);
  } catch (e) {}

  function handleBgMsg(msg) {
    if (msg.type === "STATS" && msg.data && msg.data.data) {
      const s = msg.data.data;
      setCount(statScanned, s.total_scanned || 0);
      setCount(statFlagged, s.total_flagged || 0);
      setCount(statScam, s.total_scam || 0);
    }
  }

  chrome.storage.local.get({ isEnabled: true, sensitivity: 3 }, (res) => {
    toggle.checked = res.isEnabled;
    slider.value = res.sensitivity;
    applyUIState(res.isEnabled);
    sensDesc.textContent = SENS_TEXT[res.sensitivity] || SENS_TEXT[3];
  });

  toggle.addEventListener("change", (e) => {
    const on = e.target.checked;
    chrome.storage.local.set({ isEnabled: on });
    applyUIState(on);
    chrome.runtime.sendMessage({ type: "SET_SHIELD_STATE", enabled: on });
  });

  slider.addEventListener("input", (e) => {
    sensDesc.textContent = SENS_TEXT[+e.target.value] || SENS_TEXT[3];
  });

  slider.addEventListener("change", (e) => {
    const val = +e.target.value;
    chrome.storage.local.set({ sensitivity: val });
    if (bgPort) bgPort.postMessage({ type: "SET_SENSITIVITY", value: val });
  });

  function applyUIState(on) {
    statusDot.className  = "status-dot" + (on ? "" : " off");
    statusText.textContent = on ? "Active" : "Paused";
    headerGlow.style.background = on ? "#6366f1" : "#7f1d1d";
  }

  function setCount(el, n) {
    if (el.textContent === String(n)) return;
    el.textContent = n;
    el.classList.add("popped");
    setTimeout(() => el.classList.remove("popped"), 350);
  }

  function pollStats() {
    if (bgPort) bgPort.postMessage({ type: "GET_STATS" });
  }

  pollStats();
  const interval = setInterval(pollStats, 3000);

  window.addEventListener("unload", () => {
    clearInterval(interval);
    if (bgPort) bgPort.disconnect();
  });
});
