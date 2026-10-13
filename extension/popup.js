document.addEventListener("DOMContentLoaded", () => {
  const toggle      = document.getElementById("toggleShield");
  const statusDot   = document.getElementById("statusDot");
  const statusText  = document.getElementById("statusText");
  const headerGlow  = document.getElementById("headerGlow");
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

  chrome.storage.local.get({ isEnabled: true }, (res) => {
    toggle.checked = res.isEnabled;
    applyUIState(res.isEnabled);
  });

  toggle.addEventListener("change", (e) => {
    const on = e.target.checked;
    chrome.storage.local.set({ isEnabled: on });
    applyUIState(on);
    chrome.runtime.sendMessage({ type: "SET_SHIELD_STATE", enabled: on });
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
