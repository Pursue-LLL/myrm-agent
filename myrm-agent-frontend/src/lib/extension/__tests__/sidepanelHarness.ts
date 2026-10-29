/**
 * Boots the real Side Panel (the `sidepanel.html` markup and `sidepanel.js`) against a scripted server and a stubbed
 * browser, for the controller specs.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, beforeEach, expect, vi } from 'vitest';

const EXTENSION_PANEL_DIR = resolve(__dirname, '../../../../../myrm-agent-extension/src/sidepanel');
const PANEL_HTML = readFileSync(resolve(EXTENSION_PANEL_DIR, 'sidepanel.html'), 'utf8');
const PANEL_BODY = /<body>([\s\S]*)<\/body>/.exec(PANEL_HTML)?.[1] ?? '';

type StreamBody = Record<string, unknown>;

export const element = (id: string) =>
  document.getElementById(id) as HTMLElement & HTMLButtonElement & HTMLTextAreaElement;
export const assistantBubbles = () => [...document.querySelectorAll('.message.assistant .message-bubble')];
export const overlayVisible = () => element('approval-overlay').classList.contains('visible');
export const textOf = (selector: string) => document.querySelector(selector)?.textContent;

export function sse(events: object[], status = 200): Response {
  const lines = events.map((event) => `data: ${JSON.stringify(event)}\n`).join('');
  return new Response(`${lines}data: [DONE]\n`, { status, headers: { 'Content-Type': 'text/event-stream' } });
}

const FILE_WRITE = { action: 'file_write_tool', args: { path: '/a' }, description: 'Write /a' };

/** The loop guard pause as the harness streams it (`interrupt_events` over `ToolStuckException.interrupt_payload`). */
export const LOOP_GUARD_PAUSE = {
  type: 'approval_required',
  data: {
    action_type: 'tool_stuck',
    tool_name: 'bash_code_execute_tool',
    tool_call_id: 'call-1',
    error_message: 'stuck',
  },
  messageId: 'msg-1',
  interruptId: 'interrupt-1.0',
};

/** A shell action as the harness builds it: the command, why the policy asks, and what the command does. */
export const CURL_COMMAND = 'curl -sS https://api.example.com/orders -o ~/Documents/orders.json';
export const SHELL_ACTION = {
  action: 'bash_code_execute_tool',
  args: { command: CURL_COMMAND },
  description: "Domain 'api.example.com' requires approval",
  command_spans: [{ startIndex: 0, endIndex: CURL_COMMAND.length }],
  plain_explanation: {
    en: 'Download from https://api.example.com/orders',
    zh: '从 https://api.example.com/orders 下载',
  },
};

export const approvalEvent = ({
  interruptId,
  actionRequests = [FILE_WRITE],
  ...extra
}: {
  reviewConfigs?: object[];
  extensions?: object;
  actionRequests?: object[];
  interruptId?: string;
} = {}) => ({
  type: 'tool_approval_request',
  data: { actionRequests, ...extra },
  ...(interruptId && { interruptId }),
});

/** A request the server never answers; it settles only when the panel aborts it. */
export const HANGS = Symbol('hangs');
type Served = Response | Error | typeof HANGS;

interface BootOptions {
  /** Whether the browser window the panel lives in is in front. */
  windowFocused?: boolean;
  activeTab?: { id: number; title: string; url: string };
  uiLanguage?: string;
}

interface BrowserCalls {
  notifications: { create: ReturnType<typeof vi.fn>; clear: ReturnType<typeof vi.fn> };
  messageListeners: Array<(message: object) => void>;
}

/** The browser calls of the panel booted last. */
export const browser: BrowserCalls = { notifications: { create: vi.fn(), clear: vi.fn() }, messageListeners: [] };

/** Boots the panel against `streams` (served in order to each POST /agent-stream) and returns the requests it made. */
export async function bootPanel(streams: Served[], options: BootOptions = {}): Promise<StreamBody[]> {
  const { windowFocused = true, activeTab, uiLanguage = 'en-US' } = options;
  const requests: StreamBody[] = [];
  const queue = [...streams];
  const config = { serverUrl: 'ws://localhost:25808/api/v1/ws/extension', authToken: 'token' };
  Object.assign(browser, {
    notifications: { create: vi.fn(async () => 'approval-pending'), clear: vi.fn() },
    messageListeners: [],
  });
  vi.stubGlobal('chrome', {
    storage: {
      local: {
        get: (_keys: unknown, callback?: (data: object) => void) =>
          callback ? callback(config) : Promise.resolve(config),
      },
      onChanged: { addListener: vi.fn() },
    },
    runtime: {
      onMessage: { addListener: vi.fn((listener) => browser.messageListeners.push(listener)) },
      sendMessage: vi.fn(() => Promise.resolve()),
      getURL: (path: string) => `chrome-extension://myrm/${path}`,
    },
    tabs: {
      query: vi.fn((_query: object, callback: (tabs: object[]) => void) => callback(activeTab ? [activeTab] : [])),
      onActivated: { addListener: vi.fn() },
      get: vi.fn(),
    },
    action: { openPopup: vi.fn() },
    windows: {
      getCurrent: vi.fn(async () => ({ id: 1, focused: windowFocused })),
      update: vi.fn(async () => ({})),
    },
    notifications: { ...browser.notifications, onClicked: { addListener: vi.fn() } },
    i18n: {
      getUILanguage: () => uiLanguage,
      getMessage: (key: string, substitution?: string) => (substitution === undefined ? key : `${key}:${substitution}`),
    },
  });
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string, init: { body?: string; signal?: AbortSignal }) => {
      if (input.endsWith('/api/v1/health')) {
        return new Response('{}');
      }
      requests.push(JSON.parse(init.body ?? '{}'));
      const served = queue.shift() ?? sse([]);
      if (served instanceof Error) {
        throw served;
      }
      if (served === HANGS) {
        return new Promise<Response>((_, reject) =>
          init.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError'))),
        );
      }
      return served;
    }),
  );

  vi.resetModules();
  document.body.innerHTML = PANEL_BODY;
  await import('../../../../../myrm-agent-extension/src/sidepanel/sidepanel.js');
  await vi.waitFor(() => expect(element('conn-dot').classList.contains('connected')).toBe(true));
  return requests;
}

export async function send(text: string): Promise<void> {
  element('chat-input').value = text;
  element('btn-send').click();
}

export async function sendAndAwaitApproval(): Promise<void> {
  await send('write the file');
  await vi.waitFor(() => {
    expect(overlayVisible()).toBe(true);
    expect(element('btn-reject').disabled).toBe(false);
  });
}

/** Silences the panel's own console output and restores every stub after each case. */
export function installPanelHooks(): void {
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });
}
