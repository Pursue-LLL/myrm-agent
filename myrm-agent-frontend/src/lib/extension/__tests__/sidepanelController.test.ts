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

function sse(events: object[], status = 200): Response {
  const lines = events.map((event) => `data: ${JSON.stringify(event)}\n`).join('');
  return new Response(`${lines}data: [DONE]\n`, { status, headers: { 'Content-Type': 'text/event-stream' } });
}

const approvalEvent = (extra: { reviewConfigs?: object[] } = {}) => ({
  type: 'tool_approval_request',
  data: {
    actionRequests: [{ action: 'file_write_tool', args: { path: '/a' }, description: 'Write /a' }],
    ...extra,
  },
});

/** A request the server never answers; it settles only when the panel aborts it. */
const HANGS = Symbol('hangs');
type Served = Response | Error | typeof HANGS;

/** Boots the panel against `streams` (served in order to each POST /agent-stream) and returns the requests it made. */
async function bootPanel(streams: Served[]): Promise<StreamBody[]> {
  const requests: StreamBody[] = [];
  const queue = [...streams];
  vi.stubGlobal('chrome', {
    storage: {
      local: {
        get: (_keys: string[], callback: (data: object) => void) =>
          callback({ serverUrl: 'ws://localhost:25808/api/v1/ws/extension', authToken: 'token' }),
      },
      onChanged: { addListener: vi.fn() },
    },
    runtime: { onMessage: { addListener: vi.fn() }, sendMessage: vi.fn(() => Promise.resolve()) },
    tabs: { query: vi.fn(), onActivated: { addListener: vi.fn() }, get: vi.fn() },
    action: { openPopup: vi.fn() },
    i18n: {
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

async function sendAndAwaitApproval(): Promise<void> {
  element('chat-input').value = 'write the file';
  element('btn-send').click();
  await vi.waitFor(() => {
    expect(overlayVisible()).toBe(true);
    expect(element('btn-reject').disabled).toBe(false);
  });
}

beforeEach(() => {
  vi.spyOn(console, 'error').mockImplementation(() => {});
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

    expect(element('approval-title').textContent).toBe('approvalTitleSingle:file_write_tool');
    expect(element('approval-detail').textContent).toBe('file_write_tool: Write /a');
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

    await vi.waitFor(() =>
      expect(document.querySelector('.turn-notice')?.textContent).toBe('approvalHandledElsewhere'),
    );
    expect(requests).toHaveLength(2);
    expect(assistantBubbles()[0].textContent).toBe('Hello');
    expect(assistantBubbles()[0].getAttribute('style') ?? '').not.toContain('error');
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
    expect(document.querySelector('.turn-notice')?.textContent).toBe('approvalSendFailed');
    expect(assistantBubbles()[0].textContent).toBe('Hello');
    expect(assistantBubbles()[0].getAttribute('style') ?? '').not.toContain('error');
    expect(element('btn-approve').disabled).toBe(false);

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
    expect(element('approval-detail').hidden).toBe(true);

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

    element('chat-input').value = 'read it';
    element('btn-send').click();

    await vi.waitFor(() => expect(assistantBubbles()[0].textContent).toBe('Done'));
    const steps = [...document.querySelectorAll('.message.assistant .tool-step')];
    expect(steps.map((step) => step.className)).toEqual(['tool-step done', 'tool-step error']);
    expect(steps.map((step) => step.querySelector('.name')?.textContent)).toEqual([
      'file_read_tool',
      'bash_code_execute_tool',
    ]);
  });
});
