#!/usr/bin/env bun
/** Chrome CDP clarify E2E — real UI + MiniMax-M2.7 */
import { spawnSync } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { ensureLoggedIn, authCookieHeader, apiFetch } from './subagent-dashboard-e2e-auth.mjs';

const FRONTEND = 'http://127.0.0.1:3000';
const CDP = 'http://127.0.0.1:9222';
const DEVICE_ID = process.env.E2E_CONFIG_DEVICE_ID ?? 'tauri-local';
const QUERY =
  'MUST call ask_question_tool once first. Title Framework choice. Q id framework prompt Which AI framework? Options langchain/LangChain llamaindex/LlamaIndex. requires_confirmation false. After answer reply DONE.';

function log(...args) {
  process.stderr.write(`${args.join(' ')}\n`);
}

function shell(cmd) {
  return spawnSync('bash', ['-lc', cmd], { encoding: 'utf8' });
}

function requireEnv(n) {
  const v = process.env[n];
  if (!v) throw new Error(`Missing ${n}`);
  return v;
}

function stripProviderPrefix(m) {
  return m.includes('/') ? m.split('/').slice(1).join('/') : m;
}

function inferProviderId(m) {
  return m.includes('/') ? m.split('/')[0] : 'minimax';
}

function ensureStack() {
  const ok8080 = shell('curl -sf -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/health').stdout.trim() === '200';
  const ok3000 = shell('curl -sf -o /dev/null -w "%{http_code}" --max-time 20 http://127.0.0.1:3000/').stdout.trim() === '200';
  if (ok8080 && ok3000) return;
  shell('cd /Users/yululiu/projects/AI/open-perplexity && ./myrm start');
  shell('curl -sf -o /dev/null --max-time 120 http://127.0.0.1:3000/');
}

function restartChrome() {
  shell('pkill -f "remote-debugging-port=9222" || true');
  shell('sleep 1');
  shell(
    '"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --remote-debugging-port=9222 --user-data-dir="$HOME/Library/Application Support/MyrmChromeMcp" about:blank >/dev/null 2>&1 &',
  );
  for (let i = 0; i < 15; i++) {
    if (shell(`curl -sf ${CDP}/json/version`).status === 0) return;
    shell('sleep 1');
  }
  throw new Error('Chrome CDP failed to start');
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

async function putConfig(key, value) {
  const res = await apiFetch(`/api/v1/config/${key}`, {
    method: 'PUT',
    body: JSON.stringify({ value, deviceId: DEVICE_ID }),
  });
  if (!res.ok) throw new Error(`PUT ${key}: ${(await res.text()).slice(0, 200)}`);
}

async function seedEnv() {
  const liteModel = requireEnv('LITE_MODEL');
  const liteKey = requireEnv('LITE_API_KEY');
  const liteUrl = process.env.LITE_BASE_URL?.trim() || 'https://api.minimaxi.com/v1';
  const providerId = inferProviderId(liteModel);
  const modelId = stripProviderPrefix(liteModel);
  await putConfig('providers', {
    providers: [
      {
        id: providerId,
        name: 'MiniMax',
        routingProfile: providerId,
        isBuiltIn: true,
        isEnabled: true,
        apiUrl: liteUrl,
        apiKeys: [{ key: liteKey, isActive: true }],
        enabledModels: [modelId],
        availableModels: [modelId],
        providerType: 'minimax',
      },
    ],
    defaultModelConfig: {
      baseModel: { primary: { providerId, model: modelId }, fallback: null, temperature: 0.7, modelKwargs: {} },
      liteModel: { primary: { providerId, model: modelId }, fallback: null },
      fastModeModel: null,
      routingConfig: null,
      visionFallbackModel: null,
    },
    customModelInfo: {},
  });
  await putConfig('securityConfig', { yoloModeEnabled: true, yoloModeEnabledAt: Math.floor(Date.now() / 1000) });
  const ob = await apiFetch('/api/v1/config/onboarding/complete', { method: 'POST', body: '{}' });
  if (!ob.ok) throw new Error(`onboarding: ${await ob.text()}`);
}

async function openCdpTab() {
  restartChrome();
  const res = await fetch(`${CDP}/json/new?${encodeURIComponent('about:blank')}`, { method: 'PUT' });
  if (!res.ok) throw new Error(`CDP new tab ${res.status}`);
  return res.json();
}

async function waitForTextarea(client) {
  for (let i = 0; i < 60; i++) {
    await client.evalJs(`(() => {
      for (const l of ['稍后再说','跳过此步','稍后配置','进入工作区']) {
        [...document.querySelectorAll('button')].find((b) => b.textContent?.trim() === l)?.click();
      }
    })()`);
    if (await client.evalJs(`Boolean(document.querySelector('textarea[data-chat-input], textarea'))`)) return;
    await Bun.sleep(2000);
  }
  throw new Error('textarea timeout');
}

async function fillReactTextarea(client, text) {
  const ok = await client.evalJs(`(() => {
    const el = document.querySelector('textarea[data-chat-input], textarea');
    if (!el) return false;
    el.focus();
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set;
    setter?.call(el, ${JSON.stringify(text)});
    el.dispatchEvent(new InputEvent('input', { bubbles: true, cancelable: true, inputType: 'insertText', data: ${JSON.stringify(text)} }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  })()`);
  if (!ok) throw new Error('textarea fill failed');
  await Bun.sleep(400);
}

async function typeViaKeyboard(client, text) {
  const { root } = await client.send('DOM.getDocument');
  const { nodeId } = await client.send('DOM.querySelector', {
    nodeId: root.nodeId,
    selector: 'textarea[data-chat-input], textarea',
  });
  if (!nodeId) throw new Error('textarea node missing');
  await client.send('DOM.focus', { nodeId });
  const chunk = 20;
  for (let i = 0; i < text.length; i += chunk) {
    const part = text.slice(i, i + chunk);
    for (const char of part) {
      await client.send('Input.dispatchKeyEvent', { type: 'keyDown', text: char });
      await client.send('Input.dispatchKeyEvent', { type: 'char', text: char });
      await client.send('Input.dispatchKeyEvent', { type: 'keyUp', text: char });
    }
    log(`  typed ${Math.min(i + chunk, text.length)}/${text.length}`);
  }
  await Bun.sleep(500);
}

async function clickSendWhenReady(client) {
  for (let i = 0; i < 50; i++) {
    const state = await client.evalJs(`(() => ({
      canSend: Boolean([...document.querySelectorAll('button')].find((b) => /发送|Send/.test(b.textContent || '') && !b.disabled)),
      len: document.querySelector('textarea')?.value?.length || 0,
    }))()`);
    if (state?.canSend) {
      return client.evalJs(`(() => {
        const btn = [...document.querySelectorAll('button')].find((b) => /发送|Send/.test(b.textContent || '') && !b.disabled);
        btn?.click();
        return btn ? 'click' : 'fail';
      })()`);
    }
    await Bun.sleep(200);
  }
  return 'fail';
}

async function assertMessagePersisted(chatId) {
  for (let i = 0; i < 30; i++) {
    const res = await apiFetch(`/api/v1/chats/${chatId}/messages`);
    const json = await res.json();
    const count = (json.messages || []).length;
    if (count >= 1) return count;
    await Bun.sleep(1000);
  }
  return 0;
}

async function runAttempt(attempt) {
  log(`[attempt ${attempt}] start`);
  const chatId = `chrome_clarify_${randomUUID().slice(0, 8)}`;
  await ensureLoggedIn();
  await seedEnv();
  await apiFetch('/api/v1/chats/', {
    method: 'POST',
    body: JSON.stringify({ chat_id: chatId, title: 'Chrome Clarify E2E', action_mode: 'agent', agent_id: 'builtin-general' }),
  });

  const tab = await openCdpTab();
  const client = connect(tab.webSocketDebuggerUrl);
  await client.send('Page.enable');
  await client.send('Runtime.enable');
  await client.send('Page.addScriptToEvaluateOnNewDocument', {
    source: "localStorage.setItem('auth_token','local_user_token');localStorage.setItem('actionMode','agent');",
  });
  for (const part of (authCookieHeader() || '').split(';')) {
    const [n, ...r] = part.trim().split('=');
    const v = r.join('=');
    if (n && v) await client.send('Network.setCookie', { name: n, value: v, domain: '127.0.0.1', path: '/' });
  }

  await client.send('Page.navigate', { url: `${FRONTEND}/${chatId}` });
  log(`[attempt ${attempt}] wait textarea`);
  await waitForTextarea(client);
  await client.evalJs(`(() => { [...document.querySelectorAll('[role="radio"]')].find((r) => r.textContent?.includes('智能代理'))?.click(); })()`);
  await Bun.sleep(500);

  const model = stripProviderPrefix(requireEnv('LITE_MODEL'));
  log(`[attempt ${attempt}] model ${model}`);

  await fillReactTextarea(client, QUERY);
  let sent = await clickSendWhenReady(client);
  let msgCount = await assertMessagePersisted(chatId);
  log(`[attempt ${attempt}] sent=${sent} messages=${msgCount}`);

  if (msgCount < 1) {
    log(`[attempt ${attempt}] fallback keyboard typing`);
    await typeViaKeyboard(client, QUERY);
    sent = await clickSendWhenReady(client);
    msgCount = await assertMessagePersisted(chatId);
    log(`[attempt ${attempt}] after keyboard sent=${sent} messages=${msgCount}`);
  }

  if (msgCount < 1) {
    client.ws.close();
    return { ok: false, reason: 'message_not_sent', chatId, sent, msgCount };
  }

  let clarify = null;
  for (let i = 0; i < 90; i++) {
    clarify = await client.evalJs(`(() => {
      for (const root of [...document.querySelectorAll('[class*="rounded-2xl"][class*="border"]')]) {
        const badge = [...root.querySelectorAll('span')].some((s) => /需要你确认|执行前请确认/.test(s.textContent || ''));
        const opts = [...root.querySelectorAll('button[type="button"]')].map((b) => b.textContent?.trim()).filter(Boolean);
        if (badge && opts.some((t) => t === 'LangChain' || t === 'LlamaIndex')) {
          return { amber: Boolean(root.querySelector('[class*="border-amber-500"]')), opts, title: root.querySelector('.font-semibold')?.textContent?.trim() || '' };
        }
      }
      return null;
    })()`);
    if (clarify?.opts?.length) break;
    await Bun.sleep(2000);
  }

  if (!clarify) {
    client.ws.close();
    return { ok: false, reason: 'no_clarify_form', chatId, sent, msgCount };
  }
  log(`[attempt ${attempt}] CLARIFY`, JSON.stringify(clarify));

  await client.evalJs(`(() => { [...document.querySelectorAll('button')].find((b) => b.textContent?.trim() === 'LangChain')?.click(); })()`);
  await Bun.sleep(500);
  await client.evalJs(`(() => { [...document.querySelectorAll('button')].find((b) => /^(提交|Submit)$/.test((b.textContent || '').trim()) && !b.disabled)?.click(); })()`);

  let done = false;
  for (let i = 0; i < 60; i++) {
    const text = String(await client.evalJs('document.body.innerText.slice(0, 3000)'));
    if (/DONE/i.test(text) && /langchain/i.test(text)) {
      done = true;
      break;
    }
    await Bun.sleep(2000);
  }
  client.ws.close();
  return { ok: done && !clarify.amber, chatId, model, clarify, done, sent, msgCount };
}

ensureStack();
let result = null;
for (let a = 1; a <= 2; a++) {
  result = await runAttempt(a);
  if (result.ok) break;
  if (result.reason === 'message_not_sent') continue;
  log(`[attempt ${a}] retry`);
}
log(JSON.stringify(result, null, 2));
process.exit(result?.ok ? 0 : 1);
