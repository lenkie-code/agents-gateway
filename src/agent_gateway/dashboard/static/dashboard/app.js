/**
 * Agent Gateway Dashboard — client-side behaviours
 * (Theme toggle, HTMX config, CSRF, misc)
 */

// --- Theme Management ---
const THEME_KEY = 'agw-dashboard-theme';

function applyTheme(theme) {
  const html = document.documentElement;
  html.classList.remove('dark', 'light');
  if (theme === 'dark') html.classList.add('dark');
  else if (theme === 'light') html.classList.add('light');
  // 'auto' → no class, CSS media query handles it
}

function initTheme() {
  const themeMode = document.documentElement.dataset.themeMode || 'auto';
  const saved = localStorage.getItem(THEME_KEY);
  applyTheme(saved || themeMode);
}

function toggleTheme() {
  const isDark = document.documentElement.classList.contains('dark') ||
    (!document.documentElement.classList.contains('light') &&
     window.matchMedia('(prefers-color-scheme: dark)').matches);
  const next = isDark ? 'light' : 'dark';
  localStorage.setItem(THEME_KEY, next);
  applyTheme(next);
}

document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  document.getElementById('theme-toggle')?.addEventListener('click', toggleTheme);
});

// --- HTMX: inject CSRF token on all mutating requests ---
document.addEventListener('htmx:configRequest', (event) => {
  const method = (event.detail.verb || '').toUpperCase();
  if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(method)) {
    const csrfMeta = document.querySelector('meta[name="csrf-token"]');
    if (csrfMeta) {
      event.detail.headers['X-CSRF-Token'] = csrfMeta.content;
    }
  }
});

// --- HTMX: auto-scroll chat messages area after swap ---
document.addEventListener('htmx:afterSwap', (event) => {
  const target = event.detail.target;
  // Scroll messages area to bottom
  if (target && target.id === 'messages') {
    target.scrollTop = target.scrollHeight;
  }

  // Hide loading indicator when chat response arrives
  const indicator = document.getElementById('chat-loading');
  if (indicator && target && target.id === 'messages') {
    indicator.style.display = 'none';
  }

  // Render markdown in agent message bubbles
  if (typeof marked !== 'undefined') {
    const bubbles = document.querySelectorAll('.message-assistant .message-bubble[data-raw]');
    bubbles.forEach(bubble => {
      if (!bubble.dataset.rendered) {
        bubble.innerHTML = marked.parse(bubble.dataset.raw || '');
        bubble.dataset.rendered = '1';
      }
    });
  }
});

// --- HTMX: show loading indicator when chat sends ---
document.addEventListener('htmx:beforeRequest', (event) => {
  if (event.detail.elt && event.detail.elt.id === 'chat-form') {
    const indicator = document.getElementById('chat-loading');
    if (indicator) indicator.style.display = 'flex';
  }
});

// --- Chat: Enter to send, Shift+Enter for newline ---
document.addEventListener('DOMContentLoaded', () => {
  const textarea = document.getElementById('chat-message-input');
  if (!textarea) return;

  // Auto-resize textarea
  function resizeTextarea() {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 128) + 'px';
  }

  textarea.addEventListener('input', resizeTextarea);

  textarea.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      const form = textarea.closest('form');
      if (form && textarea.value.trim()) {
        // Add user message to DOM immediately for responsiveness
        const userMsg = textarea.value.trim();
        appendUserMessage(userMsg);
        textarea.value = '';
        textarea.style.height = 'auto';
        // Trigger HTMX submit
        htmx.trigger(form, 'submit');
      }
    }
  });
});

function appendUserMessage(text) {
  const area = document.getElementById('messages');
  if (!area) return;
  const div = document.createElement('div');
  div.className = 'message message-user htmx-added';
  div.innerHTML = `
    <div class="message-avatar">U</div>
    <div class="message-bubble">${escapeHtml(text)}</div>
  `;
  area.appendChild(div);
  area.scrollTop = area.scrollHeight;
}

function escapeHtml(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

// --- Trace: toggle step detail panels ---
document.addEventListener('click', (e) => {
  const header = e.target.closest('.trace-card-header');
  if (!header) return;
  const body = header.closest('.trace-card')?.querySelector('.trace-card-body');
  if (body) {
    body.classList.toggle('hidden');
    const chevron = header.querySelector('.chevron');
    if (chevron) chevron.style.transform = body.classList.contains('hidden') ? '' : 'rotate(180deg)';
  }
});

// --- Agent selector in chat: update hidden input and reload page ---
document.addEventListener('change', (e) => {
  if (e.target && e.target.id === 'agent-selector') {
    const url = new URL(window.location.href);
    url.searchParams.set('agent_id', e.target.value);
    window.location.href = url.toString();
  }
});
