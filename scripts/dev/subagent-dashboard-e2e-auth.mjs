/**
 * Shared WebUI auth + fetch helpers for P2c subagent dashboard E2E scripts.
 */

export const apiBase = process.env.E2E_API_BASE ?? 'http://127.0.0.1:8080';
export const adminPassword = process.env.E2E_ADMIN_PASSWORD;

if (!adminPassword) {
  throw new Error('E2E_ADMIN_PASSWORD is required for WebUI E2E authentication');
}

/** @type {import('node:http').Cookie[]} */
let cookies = [];

function cookieHeader() {
  return cookies.map((c) => `${c.name}=${c.value}`).join('; ');
}

export function authCookieHeader() {
  return cookieHeader();
}

export async function apiFetch(path, options = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers ?? {}),
  };
  if (cookieHeader()) {
    headers.Cookie = cookieHeader();
  }
  const res = await fetch(`${apiBase}${path}`, {
    ...options,
    headers,
  });
  const setCookie = res.headers.getSetCookie?.() ?? [];
  for (const raw of setCookie) {
    const name = raw.split('=')[0];
    const value = raw.split('=')[1]?.split(';')[0];
    if (name && value) {
      cookies = cookies.filter((c) => c.name !== name);
      cookies.push({ name, value });
    }
  }
  return res;
}

export async function ensureLoggedIn() {
  const statusRes = await apiFetch('/webui/auth/status');
  if (!statusRes.ok) {
    throw new Error(`auth status failed: ${statusRes.status}`);
  }
  const status = await statusRes.json();
  if (!status.is_setup_done) {
    throw new Error('WebUI setup not complete; log in via Chrome first');
  }
  const loginRes = await apiFetch('/webui/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username: 'admin', password: adminPassword }),
  });
  if (!loginRes.ok) {
    throw new Error(`login failed: ${loginRes.status} ${await loginRes.text()}`);
  }
}

export async function cancelSubagent(chatId, taskId) {
  return apiFetch(`/api/v1/chats/${chatId}/subagents/${taskId}/cancel`, {
    method: 'POST',
    body: '{}',
  });
}
