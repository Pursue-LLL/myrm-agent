#!/usr/bin/env bun
/** Chrome CDP E2E: WebUI enable Browser → delegate browser subagent → example.com. */
import { spawnSync } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { apiFetch, authCookieHeader, ensureLoggedIn } from './subagent-dashboard-e2e-auth.mjs';

const ROOT = '/Users/yululiu/projects/AI/open-perplexity';
const START_CHROME = `${ROOT}/scripts/dev/start-chrome-mcp-debug.sh`;
const FRONTEND = 'http://localhost:3000';
const CDP = 'http://127.0.0.1:9222';
const QUERY = "请使用 delegate_task_tool 委派 browser 子智能体（agent_type='browser'，wait=true）：打开 https://example.com 并用 browser_snapshot_tool 抓取页面，说明 snapshot 是否包含 'Example Domain'。必须使用原生 Function Calling。";

function shell(cmd) { return spawnSync('bash', ['-lc', cmd], { encoding: 'utf8' }); }
function ensureStack() {
  for (let i = 0; i < 12; i++) {
    const b = shell('curl -sf -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/webui/auth/status');
    const f = shell('curl -sf -o /dev/null -w "%{http_code}" --max-time 90 http://127.0.0.1:3000/');
    if (b.stdout.trim() === '200' && f.stdout.trim() === '200') return;
    shell('sleep 3');
  }
  throw new Error('Stack not ready');
}
function ensureChrome() {
  if (shell(`curl -sf ${CDP}/json/version`).status === 0) return;
  shell(`bash ${START_CHROME}`);
  shell('sleep 2');
}
function connect(wsUrl) {
  let nid = 0; const pending = new Map(); const ws = new WebSocket(wsUrl);
  ws.onmessage = (e) => { const d = JSON.parse(String(e.data)); if (d.id && pending.has(d.id)) { const { resolve, reject } = pending.get(d.id); pending.delete(d.id); d.error ? reject(new Error(JSON.stringify(d.error))) : resolve(d.result); } };
  const ready = new Promise((r) => (ws.onopen = r));
  const send = async (method, params = {}) => { await ready; const id = ++nid; return new Promise((resolve, reject) => { pending.set(id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params })); }); };
  const evalJs = async (expression) => { const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails)); return r.result?.value; };
  return { send, ws, evalJs };
}
async function waitForTextarea(client, timeoutMs = 120000) {
  const steps = Math.ceil(timeoutMs / 2000);
  for (let i = 0; i < steps; i++) {
    await client.evalJs(`(() => { [...document.querySelectorAll('button,div,span')].find(el=>(el.textContent||'').includes('跳过'))?.click(); [...document.querySelectorAll('button')].find(b=>(b.textContent||'').includes('稍后再说'))?.click(); })()`);
    if (await client.evalJs(`Boolean(document.querySelector('textarea[data-chat-input], textarea'))`)) return;
    await Bun.sleep(2000);
  }
  throw new Error('textarea not found');
}
async function expandConfigPanel(client) {
  return client.evalJs(`(() => {
    const collapsed = [...document.querySelectorAll('button[aria-expanded="false"]')].find(b => {
      const label = b.getAttribute('aria-label') || '';
      return /展开|Expand/i.test(label);
    });
    collapsed?.click();
    return Boolean(collapsed);
  })()`);
}
async function enableBrowserTool(client) {
  await expandConfigPanel(client);
  await Bun.sleep(800);
  return client.evalJs(`(async () => {
    const sleep = ms => new Promise(r => setTimeout(r, ms));
    window.scrollTo(0, document.body.scrollHeight); await sleep(600);
    const builtinBtn = [...document.querySelectorAll('button')].find(b => {
      const h4 = b.querySelector('h4');
      return h4 && ((h4.textContent||'').includes('内置工具') || (h4.textContent||'').includes('Built-in'));
    });
    if (!builtinBtn) return { ok:false, reason:'no-builtin-tools-button' };
    builtinBtn.click(); await sleep(1200);
    const card = document.querySelector('[data-testid="browser"]');
    if (!card) return { ok:false, reason:'no-browser-card' };
    if (!card.className.includes('border-primary')) card.click();
    await sleep(400);
    [...document.querySelectorAll('button')].find(b => /^(确认|Confirm)$/i.test((b.textContent||'').trim()))?.click();
    await sleep(600);
    return { ok:true, hint:(document.body?.innerText||'').includes('browser 专家子 Agent') };
  })()`);
}
async function typeAndSend(client, text) {
  const { root } = await client.send('DOM.getDocument');
  const { nodeId } = await client.send('DOM.querySelector', { nodeId: root.nodeId, selector: 'textarea[data-chat-input], textarea' });
  if (!nodeId) throw new Error('textarea missing');
  await client.send('DOM.focus', { nodeId });
  await client.send('Input.insertText', { text });
  await Bun.sleep(800);
  return client.evalJs(`(() => { const btn=[...document.querySelectorAll('button.message-send-btn,button')].find(b=>/发送|Send/i.test((b.textContent||'').trim())&&!b.disabled); btn?.click(); return btn?'click':'fail'; })()`);
}
async function waitForResult(client, timeoutMs = 300000) {
  const steps = Math.ceil(timeoutMs / 3000);
  for (let i = 0; i < steps; i++) {
    let state;
    try { state = await client.evalJs(`(() => {
      const text = document.body?.innerText || '';
      if (text.includes('Not in parent toolkit') || text.includes('no tools after filtering')) return { err:true };
      if (text.includes('Example Domain')) return { ok:true };
      document.querySelector('[data-testid="subagent-dashboard-trigger"]')?.click();
      const panel = document.querySelector('[data-testid="subagent-dashboard-panel"]')?.innerText || '';
      if (panel.includes('Example Domain')) return { ok:true };
      return { ok:false };
    })()`); } catch { await Bun.sleep(2000); continue; }
    if (state?.err) return { ok:false, reason:'parent_toolkit_error' };
    if (state?.ok) return { ok:true, reason:'example_domain_seen' };
    await Bun.sleep(3000);
  }
  return { ok:false, reason:'timeout' };
}
async function main() {
  ensureStack(); ensureChrome(); await ensureLoggedIn();
  const tab = await (await fetch(`${CDP}/json/new?about:blank`, { method:'PUT' })).json();
  const client = connect(tab.webSocketDebuggerUrl);
  await client.send('Page.enable'); await client.send('Network.enable'); await client.send('Runtime.enable');
  await client.send('Page.addScriptToEvaluateOnNewDocument', { source: "localStorage.setItem('auth_token','local_user_token');localStorage.setItem('actionMode','agent');" });
  for (const part of (authCookieHeader()||'').split(';')) { const [name,...rest]=part.trim().split('='); if(name&&rest.length) await client.send('Network.setCookie',{name,value:rest.join('='),domain:'localhost',path:'/'}); }
  await client.send('Page.navigate', { url: `${FRONTEND}/` });
  await waitForTextarea(client);
  await client.evalJs(`(() => { localStorage.setItem('actionMode','agent'); [...document.querySelectorAll('[role="radio"]')].find(r => (r.textContent||'').includes('智能代理'))?.click(); })()`);
  await Bun.sleep(500);
  const browserToggle = await enableBrowserTool(client);
  const sent = await typeAndSend(client, QUERY);
  await Bun.sleep(2000);
  await client.evalJs(`(async () => { for (let i=0;i<45;i++){ if(location.pathname.length>1) return location.pathname; await new Promise(r=>setTimeout(r,1000)); } return location.pathname; })()`);
  await Bun.sleep(5000);
  const outcome = await waitForResult(client);
  const modelOnUi = await client.evalJs(`(() => [...document.querySelectorAll('button')].find(b=>/MiniMax|mimo|model/i.test(b.textContent||''))?.textContent?.trim()||'')()`);
  const chatId = await client.evalJs('location.pathname.replace(/^\\//, "")');
  client.ws.close();
  const result = { ok: outcome.ok, chatId, modelOnUi, browserToggle, sent, outcome, flow:'chrome_cdp_webui' };
  console.log(JSON.stringify(result, null, 2));
  process.exit(result.ok ? 0 : 1);
}
main().catch((e) => { console.error(e); process.exit(1); });
