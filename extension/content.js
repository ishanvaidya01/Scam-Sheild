/**
 * content.js  (v3)
 *
 * Scam Shield — content script for YouTube live chat.
 * Works for: active live chat, live chat replay, top chat, and top chat replay.
 *
 * Fix log:
 *  - Robust ID tracking: uses data attribute fallback when msg.id is empty
 *  - Multi-selector badge insertion: works across all YouTube chat DOM layouts
 *  - Observer targets multiple containers (fixes live chat replay not working)
 *  - Close (X) button on popover
 *  - No emojis anywhere
 *  - Full try/catch around every DOM operation
 */

// ── State ──────────────────────────────────────────────────────────────────────
let processedIds = new Set();
let port = null;
let isExtensionEnabled = true;
let pendingFeedback = null;

// ── Utility: simple string hash for generating fallback IDs ────────────────────
function strHash(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = Math.imul(31, h) + s.charCodeAt(i) | 0;
  }
  return 'ss-' + Math.abs(h).toString(36);
}

// ── Port management ────────────────────────────────────────────────────────────
function connectPort() {
  try {
    port = chrome.runtime.connect({ name: "chat-stream" });
    port.onMessage.addListener(handlePortMessage);
    port.onDisconnect.addListener(() => {
      port = null;
      setTimeout(connectPort, 2000);
    });
  } catch (e) {
    console.warn('[ScamShield] Port connect failed:', e);
    setTimeout(connectPort, 3000);
  }
}

// ── Global popover ─────────────────────────────────────────────────────────────
let globalPopover = document.getElementById('scam-shield-floating-popover');
if (!globalPopover) {
  globalPopover = document.createElement('div');
  globalPopover.id = 'scam-shield-floating-popover';
  globalPopover.setAttribute('role', 'dialog');
  document.body.appendChild(globalPopover);
}

// Close popover on outside click
document.addEventListener('click', (e) => {
  if (!e.target.closest('.trust-badge') && !e.target.closest('#scam-shield-floating-popover')) {
    closePopover();
  }
});

function closePopover() {
  if (globalPopover) globalPopover.style.display = 'none';
  pendingFeedback = null;
}

// ── Shield state ───────────────────────────────────────────────────────────────
function setShieldState(enabled) {
  isExtensionEnabled = enabled;
  if (!enabled) {
    document.body.classList.add('scam-shield-disabled');
    closePopover();
  } else {
    document.body.classList.remove('scam-shield-disabled');
  }
}

try {
  chrome.storage.local.get({ isEnabled: true }, (res) => setShieldState(res.isEnabled));
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === 'local' && changes.isEnabled) setShieldState(changes.isEnabled.newValue);
  });
  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === 'SET_SHIELD_STATE') setShieldState(msg.enabled);
  });
} catch (e) {
  console.warn('[ScamShield] Storage listener setup failed:', e);
}

// ── Tier configuration ────────────────────────────────────────────────────────
const TIER_CONFIG = {
  trusted:    { cls: 'trust-trusted',    icon: '✅', label: 'Trusted',    short: '✅'  },
  likely:     { cls: 'trust-likely',     icon: '🟢', label: 'Likely OK',  short: '🟢' },
  suspicious: { cls: 'trust-suspicious', icon: '⚡', label: 'Suspicious', short: '⚡' },
  high_risk:  { cls: 'trust-high-risk',  icon: '⚠️', label: 'High Risk',  short: '⚠️' },
  scam:       { cls: 'trust-scam',       icon: '🚫', label: 'Flagged',    short: '🚫' },
};

// Signal names with emoji
const SIGNAL_LABELS = {
  linguistic:   '🔤 Linguistic',
  text:         '🤖 Classifier',
  coordination: '🔗 Coordination',
  behavioral:   '👤 Behavioral',
  network:      '🕸️ Network',
};

// Reason type icons
const REASON_ICONS = {
  flag:     '🚩',
  positive: '✅',
  info:     'ℹ️',
};

// ── Signal bar HTML ────────────────────────────────────────────────────────────
function renderSignalBar(label, score) {
  const pct = Math.round(score * 100);
  const color = score >= 0.7 ? '#4ade80' : score >= 0.45 ? '#fbbf24' : '#f87171';
  return `<div class="signal-row">
    <span class="signal-label">${label}</span>
    <div class="signal-bar-track">
      <div class="signal-bar-fill" style="width:${pct}%;background:${color};"></div>
    </div>
    <span class="signal-pct">${pct}%</span>
  </div>`;
}

// ── Popover renderer ───────────────────────────────────────────────────────────
function renderPopover(data, anchorRect) {
  try {
    const { trust_score = 0.5, tier = 'suspicious', verdict = '', reasons = [], signal_breakdown = {} } = data;
    const tierConf = TIER_CONFIG[tier] || TIER_CONFIG.suspicious;
    const pct = Math.round(trust_score * 100);
    const scoreColor = trust_score >= 0.7 ? '#4ade80' : trust_score >= 0.45 ? '#fbbf24' : '#f87171';

    // Strip ONLY leading emoji/dash from verdict — preserve all spaces in the body
    const cleanVerdict = (verdict || '')
      .replace(/^[\u{1F000}-\u{1FFFF}\u{2600}-\u{27FF}✅🔵⚡⚠️🚫]+\s*/gu, '')
      .replace(/^\s*[—–-]+\s*/, '')
      .trim();

    const reasonsHtml = reasons.length > 0
      ? reasons.map(r => {
          const icon = REASON_ICONS[r.type] || '•';
          const sigLabel = SIGNAL_LABELS[r.signal] || (r.signal || '');
          // Use r.text AS-IS — do NOT strip spaces
          const reasonText = (r.text || '').trim();
          return `<li class="reason-item reason-${r.type}">
            <div class="reason-row">
              <span class="reason-icon-badge">${icon}</span>
              <span class="reason-text">${reasonText}</span>
            </div>
            <span class="reason-signal-tag">${sigLabel}</span>
          </li>`;
        }).join('')
      : `<li class="reason-item reason-positive">
           <div class="reason-row">
             <span class="reason-icon-badge">✅</span>
             <span class="reason-text">No flags triggered across all detection signals.</span>
           </div>
         </li>`;

    const barsHtml = Object.entries(signal_breakdown)
      .map(([sig, s]) => renderSignalBar(SIGNAL_LABELS[sig] || sig, s))
      .join('');

    const feedbackHtml = trust_score < 0.6
      ? `<button class="ss-feedback-btn" id="ss-mark-safe-btn">👍 Mark as safe — false positive</button>`
      : '';

    globalPopover.innerHTML = `
      <div class="popover-header">
        <div class="popover-header-left">
          <span class="popover-tier-icon">${tierConf.icon}</span>
          <span class="popover-tier-label">${tierConf.label}</span>
        </div>
        <div class="popover-header-right">
          <div class="popover-score-ring" style="--sc:${scoreColor};">
            <span class="popover-score-val">${pct}%</span>
            <span class="popover-score-sub">TRUST</span>
          </div>
          <button class="popover-close-btn" id="ss-popover-close" aria-label="Close">&#x2715;</button>
        </div>
      </div>

      ${cleanVerdict ? `<div class="popover-verdict">${cleanVerdict}</div>` : ''}

      <div class="popover-section">
        <div class="popover-section-title">DETECTION SIGNALS</div>
        <div class="signal-breakdown">${barsHtml}</div>
      </div>

      <div class="popover-section">
        <div class="popover-section-title">ANALYSIS DETAILS</div>
        <ul class="reasons-list">${reasonsHtml}</ul>
      </div>

      ${feedbackHtml}
    `;

    globalPopover.style.display = 'block';

    // Close button handler
    const closeBtn = document.getElementById('ss-popover-close');
    if (closeBtn) {
      closeBtn.addEventListener('click', (e) => { e.stopPropagation(); closePopover(); });
    }

    // Mark-as-safe handler
    const markSafeBtn = document.getElementById('ss-mark-safe-btn');
    if (markSafeBtn && pendingFeedback) {
      markSafeBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        submitFeedback({ ...pendingFeedback, reported_label: 'genuine' });
        markSafeBtn.textContent = 'Reported — thank you.';
        markSafeBtn.disabled = true;
      });
    }

    // Position: try above badge, fall back to below
    const popH = globalPopover.offsetHeight;
    const popW = globalPopover.offsetWidth || 300;
    const topAbove = anchorRect.top + window.scrollY - popH - 8;
    const topBelow = anchorRect.bottom + window.scrollY + 8;
    const useTop = anchorRect.top > popH + 20 ? topAbove : topBelow;
    const useLeft = Math.min(
      Math.max(8, anchorRect.left + window.scrollX),
      window.innerWidth - popW - 8
    );

    globalPopover.style.top = `${useTop}px`;
    globalPopover.style.left = `${useLeft}px`;
  } catch (err) {
    console.warn('[ScamShield] Popover render error:', err);
  }
}

// ── Feedback ───────────────────────────────────────────────────────────────────
function submitFeedback(feedbackData) {
  try {
    if (port) port.postMessage({ type: 'FEEDBACK', data: feedbackData });
  } catch (e) {
    console.warn('[ScamShield] Feedback send failed:', e);
  }
}

// ── Find the element that holds a given tracking ID ───────────────────────────
// YouTube live chat uses msg.id for message IDs in active streams.
// In replay mode some elements have empty or missing id attributes.
// We set a data-ss-id attribute as a stable fallback key.
function getElementByTrackingId(trackingId) {
  // First try native DOM id (works for active live chat)
  const byId = document.getElementById(trackingId);
  if (byId) return byId;
  // Fall back to data attribute (works for replay)
  return document.querySelector(`[data-ss-id="${trackingId}"]`);
}

// ── Port message handler ───────────────────────────────────────────────────────
function handlePortMessage(message) {
  try {
    if (message.type !== 'SCORE_RESULT') return;

    const data = message.data;
    const { comment_id, trust_score = 0.5, tier = 'suspicious' } = data;
    if (!comment_id) return;

    const el = getElementByTrackingId(comment_id);
    if (!el) return;
    if (el.querySelector('.trust-badge')) return; // already badged

    const tierConf = TIER_CONFIG[tier] || TIER_CONFIG.suspicious;
    const pct = Math.round(trust_score * 100);

    // Build badge
    const badge = document.createElement('span');
    badge.className = `trust-badge ${tierConf.cls}`;
    badge.dataset.commentId = comment_id;
    // Icon + score in a compact pill
    badge.innerHTML = `<span class="badge-icon">${tierConf.icon}</span><span class="badge-score">${pct}%</span>`;
    badge.setAttribute('role', 'button');
    badge.setAttribute('tabindex', '0');

    // Badge click → open popover
    badge.addEventListener('click', (e) => {
      e.stopPropagation();
      if (!isExtensionEnabled) return;
      try {
        const authorEl = el.querySelector('#author-name') || el.querySelector('[id*="author"]');
        const messageEl = el.querySelector('#message') || el.querySelector('[id*="message"]');
        pendingFeedback = {
          comment_id,
          text: messageEl?.innerText?.trim() || '',
          username: authorEl?.innerText?.trim() || '',
          trust_score,
        };
        renderPopover(data, badge.getBoundingClientRect());
      } catch (err) {
        console.warn('[ScamShield] Badge click handler error:', err);
      }
    });

    // ── Badge insertion — multi-strategy ──────────────────────────────────────
    // Strategy 1: standard author-name container (top chat + most active streams)
    const authorEl = el.querySelector('#author-name');
    if (authorEl && authorEl.parentElement) {
      authorEl.parentElement.appendChild(badge);
      return;
    }
    // Strategy 2: header element (some replay variants)
    const headerEl = el.querySelector('#header') || el.querySelector('#header-content');
    if (headerEl) {
      headerEl.appendChild(badge);
      return;
    }
    // Strategy 3: content wrapper
    const contentEl = el.querySelector('#content') || el.querySelector('#body');
    if (contentEl) {
      contentEl.appendChild(badge);
      return;
    }
    // Strategy 4: append directly to renderer element
    el.appendChild(badge);
  } catch (err) {
    console.warn('[ScamShield] handlePortMessage error:', err);
  }
}

// ── Comment extraction ─────────────────────────────────────────────────────────
// Covers: yt-live-chat-text-message-renderer (live chat + top chat)
//         yt-live-chat-paid-message-renderer  (super chats)
const MSG_SELECTORS = [
  'yt-live-chat-text-message-renderer',
  'yt-live-chat-paid-message-renderer',
].join(',');

function extractText(el) {
  // #message may contain image nodes (emojis); innerText collapses them fine
  const msgEl = el.querySelector('#message');
  if (!msgEl) return '';
  return msgEl.innerText.trim();
}

function extractAuthor(el) {
  const authorEl = el.querySelector('#author-name') || el.querySelector('[id*="author-name"]');
  return authorEl ? authorEl.innerText.trim() : '';
}

function getOrAssignId(el) {
  // Use the native id if present and non-empty
  if (el.id && el.id.trim()) return el.id.trim();
  // Otherwise use a pre-assigned tracking id
  if (el.dataset.ssId) return el.dataset.ssId;
  // Generate one from content + position
  const author = extractAuthor(el);
  const text   = extractText(el);
  const key    = author + '||' + text + '||' + el.offsetTop;
  const generated = strHash(key);
  el.dataset.ssId = generated;
  return generated;
}

function processNewComments() {
  if (!isExtensionEnabled) return;
  try {
    const messages = document.querySelectorAll(MSG_SELECTORS);
    messages.forEach((msg) => {
      try {
        const trackingId = getOrAssignId(msg);
        if (processedIds.has(trackingId)) return;

        const author = extractAuthor(msg);
        const text   = extractText(msg);
        if (!text) return; // skip messages with no text content

        processedIds.add(trackingId);

        const commentData = {
          comment_id: trackingId,
          text,
          username: author || 'unknown',
          timestamp: Date.now(),
        };

        if (port) {
          port.postMessage({ type: 'NEW_COMMENT', data: commentData });
        }
      } catch (innerErr) {
        // Never crash the forEach — just skip this message
      }
    });
  } catch (err) {
    console.warn('[ScamShield] processNewComments error:', err);
  }
}

// ── Observer setup ─────────────────────────────────────────────────────────────
// YouTube chat lives inside several possible containers depending on mode
// (live, replay, top-chat, live-chat). We observe all of them.
const observer = new MutationObserver((mutations) => {
  for (const m of mutations) {
    if (m.addedNodes.length > 0) { processNewComments(); break; }
  }
});

const CONTAINER_SELECTORS = [
  '#items.yt-live-chat-item-list-renderer',
  'yt-live-chat-item-list-renderer #items',
  'yt-live-chat-item-list-renderer',
  '#item-scroller',
  '#chat #content',
  '#chat-messages',
];

let observing = false;

function setupObserver() {
  if (observing) return;

  // Try each selector; observe any that exist
  let found = false;
  for (const sel of CONTAINER_SELECTORS) {
    const el = document.querySelector(sel);
    if (el) {
      observer.observe(el, { childList: true, subtree: true });
      found = true;
    }
  }

  if (found) {
    observing = true;
    // Run once immediately to catch messages already in DOM
    processNewComments();
    console.log('[ScamShield v3] Active — watching', CONTAINER_SELECTORS.filter(s => document.querySelector(s)));
  }
}

// Poll until chat container appears (YouTube is a SPA — chat loads async)
const initInterval = setInterval(() => {
  setupObserver();
  if (observing) clearInterval(initInterval);
}, 800);

// Re-check on URL change (YouTube SPA navigation between videos)
let lastUrl = location.href;
const navObserver = new MutationObserver(() => {
  if (location.href !== lastUrl) {
    lastUrl = location.href;
    observing = false;
    processedIds.clear();
    setTimeout(setupObserver, 1500);
  }
});
navObserver.observe(document.head, { childList: true, subtree: true });

// ── Initialize ──────────────────────────────────────────────────────────────────
connectPort();
