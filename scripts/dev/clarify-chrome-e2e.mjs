#!/usr/bin/env bun
/**
 * Chrome CDP E2E: structured clarify full user flow (real :3000 + :8080 + MiniMax-M2.7).
 * Usage: source myrm-agent-server/.env.test && bun scripts/dev/clarify-chrome-e2e.mjs
 */
import { spawnSync } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { ensureLoggedIn, authCookieHeader, apiFetch } from './subagent-dashboard-e2e-auth.mjs';

const ROOT = '/Users/yululiu/projects/AI/open-perplexity';
const START_CHROME = `${ROOT}/scripts/dev/start-chrome-mcp-debug.sh`;
const FRONTEND = 'http://127.0.0.1:3000';
const CDP = 'http://127.0.0.1:9222';

const QUERY =
  'CRITICAL: Your very first action MUST be a single ask_question_tool call — no text reply before it. ' +
  'You MUST call ask_question_tool exactly once before any other action. ' +
  'Use title "Framework choice". Ask one question with id "framework" and prompt ' +
  '"Which AI framework should I use?". Provide exactly two options: ' +
  'id "langchain" label "LangChain", id "llamaindex" label "LlamaIndex". ' +
  'Set requires_confirmation to false. Do not use bash, write_file, render_ui_tool, or any other tools. ' +
  "After you receive the user's answer, reply with a single line starting with DONE.";

function shell(cmd) {
  return spawnSync('bash', ['-lc', cmd], { encoding: 'utf8' });
}

function ensureStack() {
  const b = shell('curl -sf -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/health');
  const f = shell('curl -sf -o /dev/null -w "%{http_code}" --max-time 90 http://127.0.0.1:3000/');
  if (b.stdout.trim() !== '200' || f.stdout.trim() !== '200') {
    shell(`cd ${ROOT} && ./myrm start`);
    shell('curl -sf -o /dev/null --max-time 120 http://127.0.0.1:3000/');
  }
}

function ensureChrome() {
  if (shell(`curl -sf ${CDP}/json/version`).status === 0) return;
  shell(`bash ${START_CHROME}`);
  shell('sleep 2');
}

function connect(wsUrl) {
  let nid = 0;
  const pending = new Map();
  const ws = new WebSocket(wsUrl);
  ws.onmessage = (e) => {
    const d = JSON.parse(String(e.data));
    if (d.id && pending.has(d.id)) {
      const { resolve, reject } = pending.get(d.id);
      pending.delete(d.id);
      d.error ? reject(new Error(JSON.stringify(d.error))) : resolve(d.result);
    }
  };
  const ready = new Promise((r) => (ws.onopen = r));
  const send = async (method, params = {}) => {
    await ready;
    const id = ++nid;
    return new Promise((resolve, reject) => {
      pending.set(id, { resolve, reject });
      ws.send(JSON.stringify({ id, method, params }));
    });
  };
  const evalJs = async (expression) => {
    const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails));
    return r.result?.value;
  };
  return { send, ws, evalJs };
}

async function closeExtraTabs(keepId) {
  const tabs = await (await fetch(`${CDP}/json/list`)).json();
  for (const t of tabs) {
    if (t.id !== keepId && t.type === 'page') {
      await fetch(`${CDP}/json/close/${t.id}`, { method: 'PUT' }).catch(() => {});
    }
  }
}

async function seedLocalAuth(client) {
  await client.send('Page.addScriptToEvaluateOnNewDocument', {
    source: `(() => {
      try {
        localStorage.setItem('auth_token', 'local_user_token');
        localStorage.setItem('actionMode', 'agent');
        localStorage.setItem('dontRemindLinkDialog', 'true');
      } catch (_) {}
    })();`,
  });
}

async function createChat(chatId) {
  const res = await apiFetch('/api/v1/chats/', {
    method: 'POST',
    body: JSON.stringify({ chat_id: chatId }),
  });
  if (!res.ok) {
    throw new Error(`create chat failed: ${res.status} ${(await res.text()).slice(0, 200)}`);
  }
}
async function injectCookies(client) {
  const header = authCookieHeader();
  if (!header) return;
  for (const part of header.split(';')) {
    const [name, ...rest] = part.trim().split('=');
    const value = rest.join('=');
    if (!name || !value) continue;
    await client.send('Network.setCookie', { name, value, domain: '127.0.0.1', path: '/' });
  }
}

async function waitForTextarea(client, timeoutMs = 90000) {
  const steps = Math.ceil(timeoutMs / 2000);
  for (let i = 0; i < steps; i++) {
    const ok = await client.evalJs(`Boolean(document.querySelector('textarea[data-chat-input], textarea'))`);
    if (ok) return;
    await Bun.sleep(2000);
  }
  throw new Error(`textarea not found; url=${await client.evalJs('location.href')}`);
}

async function selectAgentMode(client) {
  await client.evalJs(`(() => {
    localStorage.setItem('actionMode', 'agent');
    const radio = [...document.querySelectorAll('[role="radio"]')].find(
      (r) => (r.textContent || '').includes('智能代理') || (r.getAttribute('aria-label') || '').includes('智能代理'),
    );
    radio?.click();
    return Boolean(radio);
  })()`);
  await Bun.sleep(500);
}

async function typeAndSend(client, text) {
  const { root } = await client.send('DOM.getDocument');
  const { nodeId } = await client.send('DOM.querySelector', {
    nodeId: root.nodeId,
    selector: 'textarea[data-chat-input], textarea',
  });
  if (!nodeId) throw new Error('textarea node missing');
  await client.send('DOM.focus', { nodeId });
  await client.send('Input.insertText', { text });
  await Bun.sleep(600);

  for (let i = 0; i < 20; i++) {
    const state = await client.evalJs(`(() => {
      const ta = document.querySelector('textarea[data-chat-input], textarea');
      const btn = [...document.querySelectorAll('button.message-send-btn, button')].find(
        (b) => /发送|Send/i.test((b.textContent || '').trim()) && !b.disabled,
      );
      return { len: ta?.value?.length || 0, canSend: Boolean(btn) };
    })()`);
    if (state?.canSend && (state?.len || 0) > 50) break;
    await Bun.sleep(300);
  }

  const sent = await client.evalJs(`(() => {
    const btn = [...document.querySelectorAll('button.message-send-btn, button')].find(
      (b) => /发送|Send/i.test((b.textContent || '').trim()) && !b.disabled,
    );
    if (btn) { btn.click(); return 'click'; }
    const form = document.querySelector('form');
    if (form?.requestSubmit) { form.requestSubmit(); return 'submit'; }
    return 'fail';
  })()`);
  return sent;
}

async function waitForClarifyForm(client, timeoutMs = 180000) {
  const steps = Math.ceil(timeoutMs / 2000);
  for (let i = 0; i < steps; i++) {
    const form = await client.evalJs(`(() => {
      const shells = [...document.querySelectorAll('[class*="rounded-2xl"][class*="border"]')];
      for (const root of shells) {
        const badge = [...root.querySelectorAll('span')].some((s) =>
          /需要你确认|执行前请确认|NEEDS CONFIRMATION|CONFIRM BEFORE/i.test(s.textContent || ''),
        );
        const opts = [...root.querySelectorAll('button[type="button"]')]
          .map((b) => b.textContent?.trim())
          .filter(Boolean);
        const hasFramework = opts.some((t) => t === 'LangChain' || t === 'LlamaIndex');
        if (badge && hasFramework) {
          return {
            amber: Boolean(root.querySelector('[class*="border-amber-500"]')),
            opts,
            title: root.querySelector('.font-semibold')?.textContent?.trim() || '',
          };
        }
      }
      return null;
    })()`);
    if (form && form.opts?.length) return form;
    await Bun.sleep(2000);
  }
  return null;
}

async function submitClarifyAnswer(client) {
  await client.evalJs(`(() => {
    const shells = [...document.querySelectorAll('[class*="rounded-2xl"][class*="border"]')];
    const root = shells.find((el) =>
      [...el.querySelectorAll('button')].some((b) => b.textContent?.trim() === 'LangChain'),
    );
    const langBtn = [...(root?.querySelectorAll('button') || [])].find(
      (b) => b.textContent?.trim() === 'LangChain',
    );
    langBtn?.click();
  })()`);
  await Bun.sleep(500);
  return client.evalJs(`(() => {
    const btn = [...document.querySelectorAll('button')].find(
      (b) => /^(提交|Submit)$/i.test((b.textContent || '').trim()) && !b.disabled,
    );
    btn?.click();
    return Boolean(btn);
  })()`);
}

async function waitForDone(client, timeoutMs = 120000) {
  const steps = Math.ceil(timeoutMs / 2000);
  for (let i = 0; i < steps; i++) {
    const text = String(await client.evalJs('document.body.innerText.slice(0, 3000)'));
    if (/DONE/i.test(text) && /langchain/i.test(text)) return true;
    await Bun.sleep(2000);
  }
  return false;
}

async function runAttempt(attempt) {
  const chatId = `chrome_clarify_${randomUUID().slice(0, 8)}`;
  ensureStack();
  ensureChrome();
  await ensureLoggedIn();
  await createChat(chatId);

  const tab = await (await fetch(`${CDP}/json/new?about:blank`, { method: 'PUT' })).json();
  await closeExtraTabs(tab.id);
  const client = connect(tab.webSocketDebuggerUrl);
  await client.send('Page.enable');
  await client.send('Network.enable');
  await client.send('Runtime.enable');
  await seedLocalAuth(client);
  await injectCookies(client);

  await client.send('Page.navigate', { url: `${FRONTEND}/${chatId}` });
  await waitForTextarea(client);
  await selectAgentMode(client);

  await client.evalJs(`(() => {
    const later = [...document.querySelectorAll('button')].find((b) => (b.textContent || '').includes('稍后再说'));
    later?.click();
  })()`);

  const sent = await typeAndSend(client, QUERY);
  console.log(`[attempt ${attempt}] SENT`, sent);

  const clarify = await waitForClarifyForm(client);
  if (!clarify) {
    const snippet = await client.evalJs('document.body.innerText.slice(0, 800)');
    client.ws.close();
    return { ok: false, reason: 'no_clarify_form', chatId, sent, snippet: String(snippet).slice(0, 300) };
  }
  console.log(`[attempt ${attempt}] CLARIFY`, clarify);

  const submitted = await submitClarifyAnswer(client);
  console.log(`[attempt ${attempt}] SUBMIT_ANSWER`, submitted);

  const done = await waitForDone(client);
  client.ws.close();
  return {
    ok: done && !clarify.amber,
    chatId,
    model: 'MiniMax-M2.7',
    clarify,
    done,
    sent,
    submitted,
  };
}

let result = null;
for (let attempt = 1; attempt <= 2; attempt++) {
  result = await runAttempt(attempt);
  if (result.ok || result.reason !== 'no_clarify_form') break;
  console.log(`[attempt ${attempt}] retrying — model may have skipped ask_question_tool`);
}

console.log(JSON.stringify(result, null, 2));
process.exit(result?.ok ? 0 : 1);
