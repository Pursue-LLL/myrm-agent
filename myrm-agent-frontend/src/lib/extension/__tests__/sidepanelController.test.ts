/**
 * Side Panel controller against the real page markup: the stream, the approval overlay and the resume request.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const EXTENSION_PANEL_DIR = resolve(__dirname, '../../../../../myrm-agent-extension/src/sidepanel');
const PANEL_HTML = readFileSync(resolve(EXTENSION_PANEL_DIR, 'sidepanel.html'), 'utf8');
const PANEL_BODY = /<body>([\s\S]*)<\/body>/.exec(PANEL_HTML)?.[1] ?? '';

type StreamBody = Record<string, unknown>;

const element = (id: string) => document.getElementById(id) as HTMLElement & HTMLButtonElement & HTMLTextAreaElement;
const assistantBubbles = () => [...document.querySelectorAll('.message.assistant .message-bubble')];
const overlayVisible = () => element('approval-overlay').classList.contains('visible');
const textOf = (selector: string) => document.querySelector(selector)?.textContent;

function sse(events: object[], status = 200): Response {
  const lines = events.map((event) => `data: ${JSON.stringify(event)}\n`).join('');
  return new Response(`${lines}data: [DONE]\n`, { status, headers: { 'Content-Type': 'text/event-stream' } });
}

const FILE_WRITE = { action: 'file_write_tool', args: { path: '/a' }, description: 'Write /a' };

/** A shell action as the harness builds it: the command, why the policy asks, and what the command does. */
const CURL_COMMAND = 'curl -sS https://api.example.com/orders -o ~/Documents/orders.json';
const SHELL_ACTION = {
  action: 'bash_code_execute_tool',
  args: { command: CURL_COMMAND },
  description: "Domain 'api.example.com' requires approval",
  command_spans: [{ startIndex: 0, endIndex: CURL_COMMAND.length }],
  plain_explanation: {
    en: 'Download from https://api.example.com/orders',
    zh: '从 https://api.example.com/orders 下载',
  },
};

const approvalEvent = ({
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
const HANGS = Symbol('hangs');
type Served = Response | Error | typeof HANGS;

interface BootOptions {
  /** Whether the browser window the panel lives in is in front. */
  windowFocused?: boolean;
  activeTab?: { id: number; title: string; url: string };
  uiLanguage?: string;
}

/** The browser calls of the panel booted last. */
let browser: {
  notifications: { create: ReturnType<typeof vi.fn>; clear: ReturnType<typeof vi.fn> };
  messageListeners: Array<(message: object) => void>;
};

/** Boots the panel against `streams` (served in order to each POST /agent-stream) and returns the requests it made. */
async function bootPanel(streams: Served[], options: BootOptions = {}): Promise<StreamBody[]> {
  const { windowFocused = true, activeTab, uiLanguage = 'en-US' } = options;
  const requests: StreamBody[] = [];
  const queue = [...streams];
  const config = { serverUrl: 'ws://localhost:25808/api/v1/ws/extension', authToken: 'token' };
  browser = {
    notifications: { create: vi.fn(async () => 'approval-pending'), clear: vi.fn() },
    messageListeners: [],
  };
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

async function send(text: string): Promise<void> {
  element('chat-input').value = text;
  element('btn-send').click();
}

async function sendAndAwaitApproval(): Promise<void> {
  await send('write the file');
  await vi.waitFor(() => {
    expect(overlayVisible()).toBe(true);
    expect(element('btn-reject').disabled).toBe(false);
  });
}

beforeEach(() => {
  vi.spyOn(console, 'error').mockImplementation(() => {});
  vi.spyOn(console, 'warn').mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('side panel approval', () => {
  it('resumes the paused turn on approve and keeps streaming into the same message', async () => {
    const requests = await bootPanel([
      sse([{ type: 'message', data: 'Hello' }, approvalEvent()]),
      sse([{ type: 'message', data: ' world' }, { type: 'message_end' }]),
    ]);
    await sendAndAwaitApproval();

    expect(element('approval-title').textContent).toBe('approvalTitleSingle');
    expect(document.querySelector('.approval-summary')).toBeNull();
    expect(element('approval-list').textContent).not.toContain('file_write_tool');
    expect(textOf('.approval-body')).toBe('path: /a');
    expect(textOf('.approval-reason')).toBe('Write /a');
    expect(element('btn-approve').hidden).toBe(false);
    expect(element('btn-reject').textContent).toBe('approvalReject');

    element('btn-approve').click();

    await vi.waitFor(() => expect(assistantBubbles()[0].textContent).toBe('Hello world'));
    expect(requests).toHaveLength(2);
    expect(requests[1]).toMatchObject({
      message_id: requests[0].message_id,
      chat_id: requests[0].chat_id,
      query: '',
      action_mode: 'agent',
      resume_value: { decision: 'approve' },
    });
    expect(assistantBubbles()).toHaveLength(1);
    expect(overlayVisible()).toBe(false);
  });

  it('shows what a shell command will do and the whole command, never the internal tool name', async () => {
    await bootPanel([sse([approvalEvent({ actionRequests: [SHELL_ACTION] })])]);
    await sendAndAwaitApproval();

    expect(textOf('.approval-summary')).toBe('Download from https://api.example.com/orders');
    expect(textOf('.approval-body')).toBe(CURL_COMMAND);
    expect(textOf('.approval-reason')).toBe("Domain 'api.example.com' requires approval");
    expect(element('approval-overlay').textContent).not.toContain('bash_code_execute_tool');
    expect(element('btn-approve').hidden).toBe(false);
  });

  it('explains the command in Chinese for a Chinese browser', async () => {
    await bootPanel([sse([approvalEvent({ actionRequests: [SHELL_ACTION] })])], { uiLanguage: 'zh-CN' });
    await sendAndAwaitApproval();

    expect(textOf('.approval-summary')).toBe('从 https://api.example.com/orders 下载');
  });

  it('writes what the agent sends as text, never as markup', async () => {
    const hostile = { ...SHELL_ACTION, args: { command: '<img src=x onerror=alert(1)>' }, description: '<b>x</b>' };
    await bootPanel([sse([approvalEvent({ actionRequests: [hostile] })])]);
    await sendAndAwaitApproval();

    expect(element('approval-overlay').querySelector('img, b')).toBeNull();
    expect(textOf('.approval-body')).toBe('<img src=x onerror=alert(1)>');
  });

  it('states when an unanswered request is settled by itself', async () => {
    await bootPanel([sse([approvalEvent({ extensions: { timeout: { seconds: 120, behavior: 'deny' } } })])]);
    await sendAndAwaitApproval();

    expect(element('approval-deadline').hidden).toBe(false);
    expect(element('approval-deadline').textContent).toMatch(/^approvalDeadlineDeny:\d{2}:\d{2}:\d{2}/);
  });

  it('shows no deadline when the request carries none', async () => {
    await bootPanel([sse([approvalEvent()])]);
    await sendAndAwaitApproval();

    expect(element('approval-deadline').hidden).toBe(true);
  });

  it('only rejects a command too long to show in full', async () => {
    const long = { ...SHELL_ACTION, args: { command: `echo ${'a'.repeat(2500)}; rm -rf ~` } };
    const requests = await bootPanel([
      sse([approvalEvent({ actionRequests: [long] })]),
      sse([{ type: 'message_end' }]),
    ]);
    await sendAndAwaitApproval();

    expect(element('btn-approve').hidden).toBe(true);
    expect(element('approval-hint').textContent).toBe('approvalHintTooLong');
    expect(textOf('.approval-body')).not.toContain('rm -rf');

    element('btn-approve').click();
    expect(requests).toHaveLength(1);

    element('btn-reject').click();
    await vi.waitFor(() => expect(requests).toHaveLength(2));
    expect(requests[1].resume_value).toMatchObject({ decision: 'reject' });
  });

  it('is announced as an alert dialog named by its title', async () => {
    await bootPanel([sse([approvalEvent()])]);
    const overlay = element('approval-overlay');

    expect(overlay.getAttribute('role')).toBe('alertdialog');
    expect(document.getElementById(overlay.getAttribute('aria-labelledby') ?? '')).toBe(element('approval-title'));
    expect(document.getElementById(overlay.getAttribute('aria-describedby') ?? '')).toBe(element('approval-list'));
  });

  it('puts focus on the safe answer when the user is working in the panel', async () => {
    await bootPanel([sse([approvalEvent()])]);
    vi.spyOn(document, 'hasFocus').mockReturnValue(true);

    await sendAndAwaitApproval();

    expect(document.activeElement).toBe(element('btn-reject'));
  });

  it('leaves focus alone when the user is somewhere else, so it cannot be pulled from the page they type in', async () => {
    await bootPanel([sse([approvalEvent()])]);
    vi.spyOn(document, 'hasFocus').mockReturnValue(false);

    await sendAndAwaitApproval();

    expect(document.activeElement).not.toBe(element('btn-reject'));
  });

  it('answers the interrupt its event named, and names none when the event named none', async () => {
    const addressed = await bootPanel([sse([approvalEvent({ interruptId: 'int-7' })]), sse([{ type: 'message_end' }])]);
    await sendAndAwaitApproval();
    element('btn-approve').click();
    await vi.waitFor(() => expect(addressed).toHaveLength(2));
    expect(addressed[1].resume_value).toEqual({ decision: 'approve', interruptId: 'int-7' });

    const unaddressed = await bootPanel([sse([approvalEvent()]), sse([{ type: 'message_end' }])]);
    await sendAndAwaitApproval();
    element('btn-approve').click();
    await vi.waitFor(() => expect(unaddressed).toHaveLength(2));
    expect(unaddressed[1].resume_value).toEqual({ decision: 'approve' });
  });

  it('sends a rejection with the denial reason', async () => {
    const requests = await bootPanel([sse([approvalEvent()]), sse([{ type: 'message_end' }])]);
    await sendAndAwaitApproval();

    element('btn-reject').click();

    await vi.waitFor(() => expect(requests).toHaveLength(2));
    expect(requests[1].resume_value).toEqual({ decision: 'reject', feedback: 'User rejected this action.' });
  });

  it('shows a notice instead of an error when the approval was already settled', async () => {
    const requests = await bootPanel([
      sse([{ type: 'message', data: 'Hello' }, approvalEvent()]),
      new Response('{"detail":"This approval has already been resolved."}', { status: 409 }),
    ]);
    await sendAndAwaitApproval();

    element('btn-approve').click();

    await vi.waitFor(() => expect(textOf('.turn-notice')).toBe('approvalHandledElsewhere'));
    expect(requests).toHaveLength(2);
    expect(assistantBubbles()[0].textContent).toBe('Hello');
    expect(assistantBubbles()[0].classList.contains('error')).toBe(false);
    expect(element('btn-send').disabled).toBe(false);
  });

  it.each([
    ['the server fails', new Response('boom', { status: 500 })],
    ['the network is down', new TypeError('Failed to fetch')],
  ])('offers the answer again when %s before it was taken', async (_label, failure) => {
    const requests = await bootPanel([
      sse([{ type: 'message', data: 'Hello' }, approvalEvent()]),
      failure,
      sse([{ type: 'message', data: ' world' }, { type: 'message_end' }]),
    ]);
    await sendAndAwaitApproval();

    element('btn-approve').click();

    await vi.waitFor(() => expect(overlayVisible()).toBe(true));
    expect(textOf('.turn-notice')).toBe('approvalSendFailed');
    expect(assistantBubbles()[0].textContent).toBe('Hello');
    expect(assistantBubbles()[0].classList.contains('error')).toBe(false);
    expect(element('btn-approve').disabled).toBe(false);
    expect(element('chat-input').disabled).toBe(true);

    element('btn-approve').click();

    await vi.waitFor(() => expect(assistantBubbles()[0].textContent).toBe('Hello world'));
    expect(requests).toHaveLength(3);
    expect(requests[2]).toMatchObject({ message_id: requests[0].message_id, resume_value: { decision: 'approve' } });
    expect(overlayVisible()).toBe(false);
  });

  it('does not offer the answer again after the user cancels the resume', async () => {
    const requests = await bootPanel([sse([approvalEvent()]), HANGS]);
    await sendAndAwaitApproval();

    element('btn-approve').click();
    await vi.waitFor(() => expect(requests).toHaveLength(2));
    element('btn-cancel').click();

    await vi.waitFor(() => expect(element('btn-send').disabled).toBe(false));
    await new Promise((resolve) => setTimeout(resolve, 20)); // lets the aborted request settle before asserting what did not happen
    expect(overlayVisible()).toBe(false);
    expect(document.querySelector('.turn-notice')).toBeNull();
  });

  it('only lets an elevated request be rejected here', async () => {
    const requests = await bootPanel([
      sse([approvalEvent({ reviewConfigs: [{ irreversibleDestructive: true }] })]),
      sse([{ type: 'message_end' }]),
    ]);
    await sendAndAwaitApproval();

    expect(element('btn-approve').hidden).toBe(true);
    expect(element('approval-hint').hidden).toBe(false);
    expect(element('approval-hint').textContent).toBe('approvalHintElevated');

    element('btn-reject').click();

    await vi.waitFor(() => expect(requests).toHaveLength(2));
    expect(requests[1].resume_value).toMatchObject({ decision: 'reject' });
  });

  it('only dismisses a request the web app has to answer', async () => {
    const requests = await bootPanel([sse([{ type: 'approval_required', data: { approval_id: 'a1' } }])]);
    await sendAndAwaitApproval();

    expect(element('btn-approve').hidden).toBe(true);
    expect(element('btn-reject').textContent).toBe('approvalDismiss');
    expect(element('approval-title').textContent).toBe('approvalTitleExternal');
    expect(element('approval-list').hidden).toBe(true);
    expect(element('approval-deadline').hidden).toBe(true);

    element('btn-reject').click();

    expect(overlayVisible()).toBe(false);
    expect(requests).toHaveLength(1);
  });

  it('drops the pending approval when the chat is reset', async () => {
    const requests = await bootPanel([sse([approvalEvent()])]);
    await sendAndAwaitApproval();

    element('btn-new-chat').click();
    element('btn-approve').click();

    expect(overlayVisible()).toBe(false);
    expect(requests).toHaveLength(1);
    expect(element('chat-input').disabled).toBe(false);
  });
});

describe('side panel input while an approval waits', () => {
  it('closes the input until the approval is answered, so a new message cannot overtake it', async () => {
    const requests = await bootPanel([sse([approvalEvent()]), sse([{ type: 'message_end' }])]);
    await sendAndAwaitApproval();

    expect(element('chat-input').disabled).toBe(true);
    expect(element('btn-send').disabled).toBe(true);
    expect(element('chat-input').placeholder).toBe('panelInputPaused');

    element('chat-input').value = 'sneaky';
    element('chat-input').dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }));
    element('btn-send').click();
    expect(requests).toHaveLength(1);
    expect(document.querySelectorAll('.message.user')).toHaveLength(1);
    expect(overlayVisible()).toBe(true);

    element('btn-reject').click();

    await vi.waitFor(() => expect(requests).toHaveLength(2));
    await vi.waitFor(() => expect(element('chat-input').disabled).toBe(false));
    expect(element('btn-send').disabled).toBe(false);
    expect(element('chat-input').placeholder).toBe('panelInputPlaceholder');
  });

  it('opens the input again when a request only the web app can answer is dismissed', async () => {
    await bootPanel([sse([{ type: 'approval_required', data: { approval_id: 'a1' } }])]);
    await sendAndAwaitApproval();
    expect(element('chat-input').disabled).toBe(true);

    element('btn-reject').click();

    expect(element('chat-input').disabled).toBe(false);
  });
});

describe('side panel approval reminder', () => {
  it('raises a system notification without the command when the browser window is not in front', async () => {
    await bootPanel([sse([approvalEvent({ actionRequests: [SHELL_ACTION] })])], { windowFocused: false });

    await sendAndAwaitApproval();

    await vi.waitFor(() => expect(browser.notifications.create).toHaveBeenCalledTimes(1));
    const [id, options] = browser.notifications.create.mock.calls[0];
    expect(id).toBe('approval-pending');
    expect(options.title).toBe('notifyApprovalTitle');
    expect(JSON.stringify(options)).not.toContain('curl');
    expect(JSON.stringify(options)).not.toContain('bash_code_execute_tool');
  });

  it('stays quiet while the user is looking at the browser', async () => {
    await bootPanel([sse([approvalEvent()])], { windowFocused: true });

    await sendAndAwaitApproval();
    await new Promise((resolve) => setTimeout(resolve, 20)); // lets the reminder decision settle before asserting what did not happen

    expect(browser.notifications.create).not.toHaveBeenCalled();
  });

  it('withdraws the notification when the approval is answered', async () => {
    await bootPanel([sse([approvalEvent()]), sse([{ type: 'message_end' }])], { windowFocused: false });
    await sendAndAwaitApproval();

    element('btn-reject').click();

    expect(browser.notifications.clear).toHaveBeenCalledWith('approval-pending');
  });
});

describe('side panel stream', () => {
  it('renders each tool call as a row in the assistant message and settles it', async () => {
    await bootPanel([
      sse([
        { type: 'tool_start', tool_name: 'file_read_tool' },
        { type: 'tool_end', tool_name: 'file_read_tool' },
        { type: 'tool_start', tool_name: 'bash_code_execute_tool' },
        { type: 'tool_failure', tool_name: 'bash_code_execute_tool' },
        { type: 'message', data: 'Done' },
        { type: 'message_end' },
      ]),
    ]);

    await send('read it');

    await vi.waitFor(() => expect(assistantBubbles()[0].textContent).toBe('Done'));
    const steps = [...document.querySelectorAll('.message.assistant .tool-step')];
    expect(steps.map((step) => step.className)).toEqual(['tool-step done', 'tool-step error']);
    expect(steps.map((step) => step.querySelector('.name')?.textContent)).toEqual([
      'file_read_tool',
      'bash_code_execute_tool',
    ]);
  });

  it('says which tool is running in the language of the UI, and goes back to thinking', async () => {
    let controller!: ReadableStreamDefaultController<Uint8Array>;
    const open = new ReadableStream<Uint8Array>({ start: (c) => void (controller = c) });
    const push = (event: object) => controller.enqueue(new TextEncoder().encode(`data: ${JSON.stringify(event)}\n`));
    await bootPanel([new Response(open, { status: 200 })]);

    await send('read it');
    push({ type: 'tool_start', tool_name: 'file_read_tool' });
    await vi.waitFor(() => expect(element('streaming-label').textContent).toBe('panelUsingTool:file_read_tool'));

    push({ type: 'tool_end', tool_name: 'file_read_tool' });
    await vi.waitFor(() => expect(element('streaming-label').textContent).toBe('panelThinking'));

    push({ type: 'message_end' });
    controller.close();
    await vi.waitFor(() => expect(element('btn-send').disabled).toBe(false));
  });

  it('tells the user something went wrong without showing the server error text', async () => {
    await bootPanel([new Response('Traceback: db password=hunter2', { status: 500 })]);

    await send('hi');

    await vi.waitFor(() => expect(assistantBubbles()[0].textContent).toBe('panelStreamError'));
    expect(assistantBubbles()[0].classList.contains('error')).toBe(true);
    expect(console.error).toHaveBeenCalled();
    expect(document.body.textContent).not.toContain('hunter2');
  });

  it('keeps the streamed text and appends the same plain message when the stream reports an error', async () => {
    await bootPanel([
      sse([
        { type: 'message', data: 'Partial' },
        { type: 'error', error: 'RuntimeError: provider quota exceeded (key sk-123)' },
      ]),
    ]);

    await send('hi');

    await vi.waitFor(() => expect(assistantBubbles()[0].textContent).toBe('Partial\n\npanelStreamError'));
    expect(document.body.textContent).not.toContain('sk-123');
  });

  it('puts the page in the language of the browser', async () => {
    await bootPanel([], { uiLanguage: 'zh-CN' });

    expect(document.documentElement.lang).toBe('zh-CN');
    expect(element('empty-state').querySelector('.title')?.textContent).toBe('panelEmptyTitle');
    expect(element('btn-new-chat').title).toBe('panelNewChat');
    expect(element('btn-cancel').title).toBe('panelCancel');
    expect(element('chat-input').placeholder).toBe('panelInputPlaceholder');
    expect(element('not-connected').textContent).toContain('panelNotConnected');
  });
});

describe('side panel page context', () => {
  const tab = { id: 4, title: 'Docs', url: 'https://example.com/a' };

  it('puts the page the user is on in front of the message', async () => {
    const requests = await bootPanel([sse([{ type: 'message_end' }])], { activeTab: tab });
    expect(textOf('#context-value')).toBe('Docs');
    expect(element('context-bar').classList.contains('visible')).toBe(true);

    await send('summarize');

    await vi.waitFor(() => expect(requests).toHaveLength(1));
    expect(requests[0].query).toBe('[Current page: Docs — https://example.com/a]\n\nsummarize');
  });

  it('leaves the page out once the user dismisses it', async () => {
    const requests = await bootPanel([sse([{ type: 'message_end' }])], { activeTab: tab });

    element('context-dismiss').click();
    await send('summarize');

    await vi.waitFor(() => expect(requests).toHaveLength(1));
    expect(requests[0].query).toBe('summarize');
    expect(element('context-bar').classList.contains('visible')).toBe(false);
  });

  it('ignores browser-internal pages', async () => {
    const requests = await bootPanel([sse([{ type: 'message_end' }])], {
      activeTab: { id: 1, title: 'Settings', url: 'chrome://settings' },
    });

    await send('hi');

    await vi.waitFor(() => expect(requests).toHaveLength(1));
    expect(requests[0].query).toBe('hi');
  });

  it('quotes the selected text in the message, once', async () => {
    const requests = await bootPanel([sse([{ type: 'message_end' }]), sse([{ type: 'message_end' }])]);
    browser.messageListeners.forEach((listener) => listener({ type: 'selected_text', text: '  a quote  ' }));
    expect(textOf('#selection-text')).toBe('a quote');
    expect(element('selection-ctx').classList.contains('visible')).toBe(true);

    await send('explain');
    await vi.waitFor(() => expect(element('btn-send').disabled).toBe(false));
    await send('and again');

    await vi.waitFor(() => expect(requests).toHaveLength(2));
    expect(requests[0].query).toBe('[Selected text: "a quote"]\n\nexplain');
    expect(requests[1].query).toBe('and again');
    expect(element('selection-ctx').classList.contains('visible')).toBe(false);
  });

  it('takes the question of a context-menu ask along with its selection', async () => {
    await bootPanel([]);

    browser.messageListeners.forEach((listener) =>
      listener({ type: 'context_menu_query', text: 'selected', prompt: 'What is this?' }),
    );

    expect(element('chat-input').value).toBe('What is this?');
    expect(textOf('#selection-text')).toBe('selected');
  });
});
