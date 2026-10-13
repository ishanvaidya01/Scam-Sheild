/**
 * content.js
 *
 * Scam Shield — content script for YouTube live chat.
 * Badges messages with: Clear, Suspicious, Likely Campaign, or Unverifiable.
 * Popover displays the top 3 evidence items.
 */

let processedIds = new Set();
let port = null;
let isExtensionEnabled = true;

function strHash(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = Math.imul(31, h) + s.charCodeAt(i) | 0;
  }
  return 'ss-' + Math.abs(h).toString(36);
}

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

let globalPopover = document.getElementById('scam-shield-floating-popover');
if (!globalPopover) {
  globalPopover = document.createElement('div');
  globalPopover.id = 'scam-shield-floating-popover';
  globalPopover.setAttribute('role', 'dialog');
  document.body.appendChild(globalPopover);
}

document.addEventListener('click', (e) => {
  if (!e.target.closest('.trust-badge') && !e.target.closest('#scam-shield-floating-popover')) {
    closePopover();
  }
});

function closePopover() {
  if (globalPopover) globalPopover.style.display = 'none';
}

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

// ── 3-State Verdict Configuration (+ Unverifiable) ──────────────────────────
const VERDICT_CONFIG = {
  clear:           { cls: 'trust-trusted',    icon: '✅', label: 'Clear' },
  suspicious:      { cls: 'trust-suspicious', icon: '⚡', label: 'Suspicious' },
  likely_campaign: { cls: 'trust-scam',       icon: '🚫', label: 'Likely Campaign' },
  unverifiable:    { cls: 'trust-likely',     icon: '❓', label: 'Unverifiable' },
};

function renderPopover(data, anchorRect) {
  try {
    const {
      trust_score = 0.5,
      verdict = 'suspicious',
      verdict_label = 'Suspicious',
      unverifiable = false,
      reasons = [],
    } = data;

    const key = unverifiable ? 'unverifiable' : (verdict in VERDICT_CONFIG ? verdict : 'suspicious');
    const conf = VERDICT_CONFIG[key];
    const pct = Math.round(trust_score * 100);
    const scoreColor = conf.cls === 'trust-trusted' ? '#4ade80' : conf.cls === 'trust-suspicious' ? '#fbbf24' : '#f87171';

    // Top 3 evidence items
    const topReasons = (reasons || []).slice(0, 3);
    const reasonsHtml = topReasons.length > 0
      ? topReasons.map((r) => {
          const icon = r.type === 'positive' ? '✅' : '🚩';
          const signalTag = r.signal ? `<span class="reason-signal-tag">${r.signal}</span>` : '';
          return `<li class="reason-item reason-${r.type || 'flag'}">
            <div class="reason-row">
              <span class="reason-icon-badge">${icon}</span>
              <span class="reason-text">${(r.text || '').trim()}</span>
            </div>
            ${signalTag}
          </li>`;
        }).join('')
      : `<li class="reason-item reason-positive">
           <div class="reason-row">
             <span class="reason-icon-badge">ℹ️</span>
             <span class="reason-text">No significant anomaly or coordination flags detected.</span>
           </div>
         </li>`;

    globalPopover.innerHTML = `
      <div class="popover-header">
        <div class="popover-header-left">
          <span class="popover-tier-icon">${conf.icon}</span>
          <span class="popover-tier-label">${conf.label}</span>
        </div>
        <div class="popover-header-right">
          <div class="popover-score-ring" style="--sc:${scoreColor};">
            <span class="popover-score-val">${pct}%</span>
            <span class="popover-score-sub">TRUST</span>
          </div>
          <button class="popover-close-btn" id="ss-popover-close" aria-label="Close">&#x2715;</button>
        </div>
      </div>

      <div class="popover-section">
        <div class="popover-section-title">TOP EVIDENCE (MAX 3)</div>
        <ul class="reasons-list">${reasonsHtml}</ul>
      </div>
    `;

    globalPopover.style.display = 'block';

    const closeBtn = document.getElementById('ss-popover-close');
    if (closeBtn) {
      closeBtn.addEventListener('click', (e) => { e.stopPropagation(); closePopover(); });
    }

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

function getElementByTrackingId(trackingId) {
  const byId = document.getElementById(trackingId);
  if (byId) return byId;
  return document.querySelector(`[data-ss-id="${trackingId}"]`);
}

function handlePortMessage(message) {
  try {
    if (message.type !== 'SCORE_RESULT') return;

    const data = message.data;
    const { comment_id, trust_score = 0.5, verdict = 'suspicious', unverifiable = false } = data;
    if (!comment_id) return;

    const el = getElementByTrackingId(comment_id);
    if (!el) return;
    if (el.querySelector('.trust-badge')) return;

    const key = unverifiable ? 'unverifiable' : (verdict in VERDICT_CONFIG ? verdict : 'suspicious');
    const conf = VERDICT_CONFIG[key];

    const badge = document.createElement('span');
    badge.className = `trust-badge ${conf.cls}`;
    badge.dataset.commentId = comment_id;
    badge.innerHTML = `<span class="badge-icon">${conf.icon}</span><span class="badge-score">${conf.label}</span>`;
    badge.setAttribute('role', 'button');
    badge.setAttribute('tabindex', '0');

    badge.addEventListener('click', (e) => {
      e.stopPropagation();
      if (!isExtensionEnabled) return;
      renderPopover(data, badge.getBoundingClientRect());
    });

    const authorEl = el.querySelector('#author-name');
    if (authorEl && authorEl.parentElement) {
      authorEl.parentElement.appendChild(badge);
      return;
    }
    const headerEl = el.querySelector('#header') || el.querySelector('#header-content');
    if (headerEl) {
      headerEl.appendChild(badge);
      return;
    }
    const contentEl = el.querySelector('#content') || el.querySelector('#body');
    if (contentEl) {
      contentEl.appendChild(badge);
      return;
    }
    el.appendChild(badge);
  } catch (err) {
    console.warn('[ScamShield] handlePortMessage error:', err);
  }
}

const MSG_SELECTORS = [
  'yt-live-chat-text-message-renderer',
  'yt-live-chat-paid-message-renderer',
].join(',');

function extractText(el) {
  const msgEl = el.querySelector('#message');
  if (!msgEl) return '';
  return msgEl.innerText.trim();
}

function extractAuthor(el) {
  const authorEl = el.querySelector('#author-name') || el.querySelector('[id*="author-name"]');
  return authorEl ? authorEl.innerText.trim() : '';
}

function extractBadges(el) {
  const badges = [];
  if (el.querySelector('yt-live-chat-author-badge-renderer[type="member"]')) badges.push('member');
  if (el.querySelector('yt-live-chat-author-badge-renderer[type="moderator"]')) badges.push('moderator');
  if (el.querySelector('yt-live-chat-author-badge-renderer[type="verified"]')) badges.push('verified');
  return badges;
}

function getOrAssignId(el) {
  if (el.id && el.id.trim()) return el.id.trim();
  if (el.dataset.ssId) return el.dataset.ssId;
  const author = extractAuthor(el);
  const text = extractText(el);
  const key = author + '||' + text + '||' + el.offsetTop;
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
        const text = extractText(msg);
        if (!text) return;

        processedIds.add(trackingId);

        const commentData = {
          comment_id: trackingId,
          text,
          username: author || 'unknown',
          timestamp: Date.now(),
          badges: extractBadges(msg),
        };

        if (port) {
          port.postMessage({ type: 'NEW_COMMENT', data: commentData });
        }
      } catch (innerErr) {}
    });
  } catch (err) {
    console.warn('[ScamShield] processNewComments error:', err);
  }
}

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
    processNewComments();
    console.log('[ScamShield] Active observer connected.');
  }
}

const initInterval = setInterval(() => {
  setupObserver();
  if (observing) clearInterval(initInterval);
}, 800);

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

connectPort();
