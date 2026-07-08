#!/usr/bin/env bun
/**
 * Chrome CDP E2E: enable Browser in WebUI config panel → delegate browser subagent → example.com.
 * Usage: source myrm-agent-server/.env.test && bun scripts/dev/browser-delegate-chrome-e2e.mjs
 */
import { spawnSync } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { apiFetch, authCookieHeader, ensureLoggedIn } from './subagent-dashboard-e2e-auth.mjs';

const ROOT = '/Users/yululiu/projects/AI/open-perplexity';
const START_CHROME = `${ROOT}/scripts/dev/start-chrome-mcp-debug.sh`;
const FRONTEND = 'http://127.0.0.1:3000';
const CDP = 'http://127.0.0.1:9222';
const deviceId = process.env.E2E_CONFIG_DEVICE_ID ?? 'tauri-local';

const QUERY =
  "请使用 delegate_task_tool 工具委派 browser 子智能体：agent_type 必须为 'browser'，wait 设为 true，任务为打开 https://example.com 并用 browser_snapshot_tool 抓取页面，在最终回复中说明 snapshot 是否包含 'Example Domain'。必须使用原生 Function Calling。";

function shell(cmd) {
  return spawnSync('bash', ['-lc', cmd], { encoding: 'utf8' });
}

function requireEnv(name) {
  const value = process.env[name];
  if (!value) throw new Error(`Missing ${name}`);
  return value;
}

function modelLabel() {
  const raw = requireEnv('BASIC_MODEL');
  return raw.includes('/') ? raw.split('/').slice(1).join('/') : raw;
}

async function putConfig(configKey, value) {
  const res = await apiFetch(`/api/v1/config/${configKey}`, {
    method: 'PUT',
    body: JSON.stringify({ value, deviceId }),
  });
  if (!res.ok) throw new Error(`PUT /config/${configKey}: ${await res.text()}`);
}

async function seedProviders() {
  const basicModel = requireEnv('BASIC_MODEL');
  const basicKey = requireEnv('BASIC_API_KEY');
  const basicUrl = process.env.BASIC_BASE_URL;
  const providerId = basicModel.includes('/') ? basicModel.split('/')[0] : 'minimax';
  const modelId = modelLabel();
  await putConfig('providers', {
    providers: [
      {
        id: providerId,
        name: providerId,
        routingProfile: providerId,
        isBuiltIn: providerId === 'minimax',
        isEnabled: true,
        apiUrl: basicUrl?.trim() || 'https://api.minimaxi.com/v1',
        apiKeys: [{ key: basicKey, isActive: true }],
        enabledModels: [modelId],
        availableModels: [modelId],
        providerType: providerId === 'minimax' ? 'minimax' : 'openai',
      },
    ],
    defaultModelConfig: {
      baseModel: { primary: { providerId, model: modelId }, fallback: null, temperature: 0.7, modelKwargs: {} },
      liteModel: { primary: null, fallback: null },
      fastModeModel: null,
      routingConfig: null,
      visionFallbackModel: null,
    },
    customModelInfo: {},
  });
}

function ensureStack() {
  const b = shell('curl -sf -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/webui/auth/status');
  const f = shell('curl -sf -o /dev/null -w "%{http_code}" --max-time 30 http://127.0.0.1:3000/');
  if (b.stdout.trim() !== '200' || f.stdout.trim() !== '200') {
    throw new Error(`Stack not ready backend=${b.stdout.trim()} frontend=${f.stdout.trim()}`);
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
      (r) => (r.textContent || '').includes('智能代理') || (r.getAttribute('aria-label') || '').includes('Agent'),
    );
    radio?.click();
    return Boolean(radio);
  })()`);
  await Bun.sleep(500);
}

async function selectBaseModel(client) {
  const model = modelLabel();
  return client.evalJs(`(async () => {
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    const trigger = [...document.querySelectorAll('button')].find((b) =>
      /MiniMax|mimo|未配置|not configured|model/i.test(b.textContent || ''),
    );
    if (!trigger) return { ok: false, reason: 'no-trigger' };
    trigger.click();
    await sleep(700);
    const option = [...document.querySelectorAll('button, [role="option"], [data-model]')].find((el) =>
      (el.textContent || '').includes(${JSON.stringify(model)}),
    );
    if (!option) return { ok: false, reason: 'no-option', model: ${JSON.stringify(model)} };
    option.click();
    await sleep(400);
    const label = [...document.querySelectorAll('button')].find((b) =>
      (b.textContent || '').includes(${JSON.stringify(model)}),
    );
    return { ok: Boolean(label), model: ${JSON.stringify(model)} };
  })()`);
}

async function enableBrowserTool(client) {
  return client.evalJs(`(() => {
    const card = document.querySelector('[data-testid="browser"]');
    if (!card) return { ok: false, reason: 'no-browser-card' };
    const checked = card.className.includes('border-primary');
    if (!checked) card.click();
    const bodyText = document.body?.innerText || '';
    const hint = bodyText.includes('browser 专家子 Agent') ||
      bodyText.includes('browser specialist');
    return { ok: true, checked: card.className.includes('border-primary'), hintVisible: hint };
  })()`);
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
  return client.evalJs(`(() => {
    const btn = [...document.querySelectorAll('button.message-send-btn, button')].find(
      (b) => /发送|Send/i.test((b.textContent || '').trim()) && !b.disabled,
    );
    if (btn) { btn.click(); return 'click'; }
    return 'fail';
  })()`);
}

async function waitForBrowserDelegateResult(client, timeoutMs = 300000) {
  const steps = Math.ceil(timeoutMs / 3000);
  for (let i = 0; i < steps; i++) {
    const state = await client.evalJs(`(() => {
      const body = document.body;
      if (!body) return { pending: true };
      const text = body.innerText || '';
      const hasExample = text.includes('Example Domain');
      const hasParentToolkitError = text.includes('Not in parent toolkit') ||
        text.includes('no tools after filtering');
      const dash = document.querySelector('[data-testid="subagent-dashboard-trigger"]');
      const panel = document.querySelector('[data-testid="subagent-dashboard-panel"]');
      if (dash && !panel) dash.click();
      const panelText = panel?.innerText || '';
      return {
        pending: false,
        hasExample: hasExample || panelText.includes('Example Domain'),
        hasError: hasParentToolkitError,
        dashVisible: Boolean(dash),
        panelText: panelText.slice(0, 400),
        snippet: text.slice(0, 1200),
      };
    })()`);
    if (state?.pending) {
      await Bun.sleep(1000);
      continue;
    }
    if (state?.hasError) {
      return { ok: false, reason: 'parent_toolkit_error', ...state };
    }
    if (state?.hasExample) {
      return { ok: true, reason: 'example_domain_seen', ...state };
    }
    await Bun.sleep(3000);
  }
  return { ok: false, reason: 'timeout' };
}

async function main() {
  ensureStack();
  ensureChrome();
  await ensureLoggedIn();
  try {
    await putConfig('securityConfig', {
      yoloModeEnabled: true,
      yoloModeEnabledAt: Math.floor(Date.now() / 1000),
    });
  } catch {
    /* yolo optional if already set in WebUI */
  }

  const chatId = randomUUID();
  const chatRes = await apiFetch('/api/v1/chats/', {
    method: 'POST',
    body: JSON.stringify({
      chat_id: chatId,
      title: `Chrome Browser Delegate ${Date.now()}`,
      action_mode: 'agent',
      agent_id: 'builtin-general',
      messages: [],
    }),
  });
  if (!chatRes.ok) throw new Error(`create chat: ${await chatRes.text()}`);

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
  const modelPick = await selectBaseModel(client);
  const browserToggle = await enableBrowserTool(client);

  await client.evalJs(`(() => {
    const later = [...document.querySelectorAll('button')].find((b) => (b.textContent || '').includes('稍后再说'));
    later?.click();
  })()`);

  const sent = await typeAndSend(client, QUERY);
  const outcome = await waitForBrowserDelegateResult(client);
  client.ws.close();

  const result = {
    ok: outcome.ok,
    chatId,
    model: modelLabel(),
    modelPick,
    browserToggle,
    sent,
    outcome,
    flow: 'chrome_cdp_frontend_3000',
  };
  console.log(JSON.stringify(result, null, 2));
  process.exit(result.ok ? 0 : 1);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
