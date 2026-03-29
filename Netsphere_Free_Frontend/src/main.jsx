import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

const RESET_QUERY_KEY = 'nm_reset';
const RESET_GUARD_KEY = 'nm_reset_guard';
const RESET_GUARD_TTL_MS = 30 * 1000;

const shouldSkipReset = () => {
  try {
    const raw = sessionStorage.getItem(RESET_GUARD_KEY);
    if (!raw) return false;
    const ts = Number(raw);
    return Number.isFinite(ts) && (Date.now() - ts) < RESET_GUARD_TTL_MS;
  } catch (_e) {
    return false;
  }
};

const markResetGuard = () => {
  try {
    sessionStorage.setItem(RESET_GUARD_KEY, String(Date.now()));
  } catch (_e) {
    // ignore storage errors
  }
};

const clearClientState = async () => {
  try { localStorage.clear(); } catch (_e) { /* ignore */ }
  try { sessionStorage.clear(); } catch (_e) { /* ignore */ }

  if (typeof window !== 'undefined' && 'caches' in window) {
    try {
      const keys = await caches.keys();
      await Promise.all(keys.map((k) => caches.delete(k)));
    } catch (_e) {
      // ignore cache API errors
    }
  }

  if (typeof navigator !== 'undefined' && navigator.serviceWorker && navigator.serviceWorker.getRegistrations) {
    try {
      const regs = await navigator.serviceWorker.getRegistrations();
      await Promise.all(regs.map((r) => r.unregister()));
    } catch (_e) {
      // ignore SW errors
    }
  }
};

const hardRecover = async () => {
  if (shouldSkipReset()) return;
  markResetGuard();
  await clearClientState();
  try {
    const url = new URL(window.location.href);
    url.searchParams.delete(RESET_QUERY_KEY);
    window.location.replace(url.toString());
  } catch (_e) {
    window.location.reload();
  }
};

if (typeof window !== 'undefined') {
  const params = new URLSearchParams(window.location.search);
  if (params.get(RESET_QUERY_KEY) === '1') {
    // manual recovery hook: /?nm_reset=1
    void hardRecover();
  }

  // Vite dynamic chunk mismatch recovery.
  window.addEventListener('vite:preloadError', (event) => {
    try { event.preventDefault(); } catch (_e) { /* ignore */ }
    void hardRecover();
  });

  // Fallback for other chunk-load failures.
  window.addEventListener('error', (event) => {
    const msg = String(event?.message || '');
    if (msg.includes('Loading chunk') || msg.includes('Failed to fetch dynamically imported module')) {
      void hardRecover();
    }
  });
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
