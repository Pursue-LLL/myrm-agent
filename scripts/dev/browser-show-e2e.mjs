#!/usr/bin/env node
/**
 * `myrm browser show` — bring the E2E Chrome's (:9333) current test window
 * in front of the human so they can watch a test run.
 *
 * Talks straight to Chrome's CDP endpoints on the orchestrator's port
 * (MYRM_E2E_CDP_PORT, default 9333). The orchestrator parks windows only
 * when it creates them, so un-parking an existing window never fights it;
 * pages created afterwards keep parking offscreen as usual. The only CDP
 * writes are window bounds + activation — no effect on the running test
 * beyond where its window sits.
 */
import { pathToFileURL } from 'node:url';

const PORT = Number(process.env.MYRM_E2E_CDP_PORT ?? 9333);
const BASE = `http://127.0.0.1:${PORT}`;

/** Most recent real page wins; blank pool pages are the fallback. */
export function pickShowPage(pages) {
  let lastPage = null;
  let lastRealPage = null;
  for (const page of pages) {
    if (!page || page.type !== 'page' || !(page.id ?? page.targetId)) continue;
    lastPage = page;
    if (page.url && page.url !== 'about:blank') lastRealPage = page;
  }
  return lastRealPage ?? lastPage;
}

async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} -> HTTP ${res.status}`);
  return res.json();
}

function cdpSend(ws) {
  let seq = 0;
  const pending = new Map();
  ws.addEventListener('message', (ev) => {
    const msg = JSON.parse(ev.data);
    if (!msg.id || !pending.has(msg.id)) return;
    const { resolve, reject } = pending.get(msg.id);
    pending.delete(msg.id);
    if (msg.error) reject(new Error(msg.error.message));
    else resolve(msg.result);
  });
  return (method, params = {}) =>
    new Promise((resolve, reject) => {
      const id = ++seq;
      pending.set(id, { resolve, reject });
      ws.send(JSON.stringify({ id, method, params }));
    });
}

async function main() {
  let version;
  try {
    version = await fetchJson(`${BASE}/json/version`);
  } catch {
    console.error(
      'E2E Chrome 没在跑（没有测试运行时它通常是关着的）——等测试跑起来再敲，或先 ./myrm chrome-e2e start',
    );
    process.exit(1);
  }
  const pages = (await fetchJson(`${BASE}/json/list`)).filter((t) => t.type === 'page');
  const page = pickShowPage(pages);
  if (!page) {
    console.error('E2E Chrome 在跑，但当前没有测试页面。');
    process.exit(1);
  }
  const targetId = page.id ?? page.targetId;
  const ws = new WebSocket(version.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    ws.addEventListener('open', resolve, { once: true });
    ws.addEventListener('error', reject, { once: true });
  });
  try {
    const send = cdpSend(ws);
    const { windowId, bounds } = await send('Browser.getWindowForTarget', { targetId });
    await send('Browser.setWindowBounds', {
      windowId,
      bounds: {
        windowState: 'normal',
        left: 0,
        top: 0,
        width: bounds.width,
        height: bounds.height,
      },
    });
    await send('Target.activateTarget', { targetId });
  } finally {
    ws.close();
  }
  console.log(`已把测试窗口弹到屏幕上：${page.url || 'about:blank'}`);
  console.error('围观别上手点页面（会干扰正在跑的用例）；看完不用管，测试结束窗口自动关。');
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((e) => {
    console.error(`browser show failed: ${e.message}`);
    process.exit(1);
  });
}
