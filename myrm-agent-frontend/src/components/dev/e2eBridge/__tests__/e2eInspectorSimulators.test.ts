/**
 * The inspector simulators drive the product's real SSE handlers with one synthetic assistant message.
 *
 * Real scenario: BLCV E2E runs call `simulate*` to put a browser or desktop view into the inspector stores; the handler
 * only sees what the simulator hands it, so a context that loses a field or shares state between calls changes what
 * the E2E asserts without any type error.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { createInspectorMembers } from '@/components/dev/e2eBridge/members/inspectors';
import { AgentEventType } from '@/store/chat/types';

const handlers = vi.hoisted(() => ({ fileDiffEvents: vi.fn(), toolLifecycleEvents: vi.fn() }));
vi.mock('@/store/chat/messageStream/handlers/fileDiffEvents', () => ({ fileDiffEvents: handlers.fileDiffEvents }));
vi.mock('@/store/chat/messageStream/handlers/toolLifecycleEvents', () => ({
  toolLifecycleEvents: handlers.toolLifecycleEvents,
}));

type Simulator = (...args: unknown[]) => Promise<unknown>;
const members = createInspectorMembers() as unknown as Record<string, Simulator>;

interface HandlerContext {
  data: { type: string; messageId: string };
  input: string;
  sources: undefined;
  added: boolean;
  recievedMessage: string;
  files: unknown[];
  state: {
    messages: { messageId: string; chatId: string; role: string; content: string; createdAt: Date }[];
    messageAppeared: boolean;
    loading: boolean;
    scheduler: object;
  };
  actions: Record<string, (...args: unknown[]) => unknown>;
}

const SIMULATORS = [
  {
    name: 'simulateBrowserViewUpdate',
    handler: handlers.fileDiffEvents,
    eventType: AgentEventType.BROWSER_VIEW_UPDATE,
    messageIdPattern: /^e2e-blvc-view-\d+$/,
    loading: false,
  },
  {
    name: 'simulateBrowserToolStart',
    handler: handlers.toolLifecycleEvents,
    eventType: AgentEventType.TOOL_START,
    messageIdPattern: /^e2e-blvc-tool-\d+$/,
    loading: false,
  },
  {
    name: 'simulateDesktopViewUpdate',
    handler: handlers.fileDiffEvents,
    eventType: AgentEventType.DESKTOP_VIEW_UPDATE,
    messageIdPattern: /^e2e-blvc-desktop-\d+$/,
    loading: false,
  },
  {
    name: 'simulateDesktopControlApprovalRequest',
    handler: handlers.fileDiffEvents,
    eventType: AgentEventType.DESKTOP_CONTROL_APPROVAL_REQUEST,
    messageIdPattern: /^e2e-blvc-desktop-approval-\d+$/,
    loading: true,
  },
] as const;

/** The context the handler received in its only call. */
function receivedContext(handler: (typeof SIMULATORS)[number]['handler']): HandlerContext {
  expect(handler).toHaveBeenCalledTimes(1);
  return handler.mock.calls[0][0] as HandlerContext;
}

beforeEach(() => {
  handlers.fileDiffEvents.mockReset().mockResolvedValue(null);
  handlers.toolLifecycleEvents.mockReset().mockResolvedValue(null);
});

describe.each(SIMULATORS)('$name', ({ name, handler, eventType, messageIdPattern, loading }) => {
  it('hands the handler its event and one assistant message of the trimmed chat', async () => {
    await members[name]('  chat-1 ');

    const ctx = receivedContext(handler);
    expect(ctx.data.type).toBe(eventType);
    expect(ctx.data.messageId).toMatch(messageIdPattern);
    expect(ctx).toMatchObject({
      input: '',
      sources: undefined,
      added: false,
      recievedMessage: '',
      files: [],
      state: {
        messageAppeared: false,
        loading,
        scheduler: {},
        messages: [{ messageId: ctx.data.messageId, chatId: 'chat-1', role: 'assistant', content: '' }],
      },
    });
    expect(ctx.state.messages).toHaveLength(1);
    expect(ctx.state.messages[0].createdAt).toBeInstanceOf(Date);
  });

  it('carries exactly the context fields the handlers read', async () => {
    await members[name]('chat-1');

    const ctx = receivedContext(handler);
    expect(Object.keys(ctx).sort()).toEqual([
      'actions',
      'added',
      'data',
      'files',
      'input',
      'recievedMessage',
      'sources',
      'state',
    ]);
    expect(Object.keys(ctx.actions).sort()).toEqual([
      '_processSuggestions',
      'scheduleAutoSave',
      'setLoading',
      'setMessageAppeared',
      'setMessages',
    ]);
  });

  it('gives the handler store actions that change nothing', async () => {
    await members[name]('chat-1');

    const { actions } = receivedContext(handler);
    expect(actions.setMessages(() => undefined)).toBeUndefined();
    expect(actions.setMessageAppeared(true)).toBeUndefined();
    expect(actions.setLoading(true)).toBeUndefined();
    expect(actions.scheduleAutoSave()).toBeUndefined();
    await expect(actions._processSuggestions({})).resolves.toBeUndefined();
  });

  it('builds a fresh context for every call', async () => {
    await members[name]('chat-1');
    await members[name]('chat-1');

    expect(handler).toHaveBeenCalledTimes(2);
    const [first, second] = handler.mock.calls.map(([ctx]) => ctx as HandlerContext);
    expect(first.state).not.toBe(second.state);
    expect(first.state.messages).not.toBe(second.state.messages);
    expect(first.actions).not.toBe(second.actions);
  });
});

describe('the simulator guards and results', () => {
  it.each(SIMULATORS.map((sim) => sim.name))('%s rejects a blank chat id without driving a handler', async (name) => {
    const args = name === 'simulateBrowserToolStart' ? ['   ', 'browser_navigate_tool'] : ['   '];
    await expect(members[name](...args)).resolves.toEqual({
      ok: false,
      reason: name === 'simulateBrowserToolStart' ? 'invalid-args' : 'empty-chat-id',
    });
    expect(handlers.fileDiffEvents).not.toHaveBeenCalled();
    expect(handlers.toolLifecycleEvents).not.toHaveBeenCalled();
  });

  it('simulateBrowserToolStart accepts only browser tools and reports the trimmed names', async () => {
    await expect(members.simulateBrowserToolStart('chat-1', 'desktop_click_tool')).resolves.toEqual({
      ok: false,
      reason: 'invalid-args',
    });
    expect(handlers.toolLifecycleEvents).not.toHaveBeenCalled();

    await expect(members.simulateBrowserToolStart(' chat-1 ', ' browser_click_tool ')).resolves.toEqual({
      ok: true,
      chatId: 'chat-1',
      toolName: 'browser_click_tool',
    });
    expect(receivedContext(handlers.toolLifecycleEvents).data).toMatchObject({ tool_name: 'browser_click_tool' });
  });

  it.each(['simulateBrowserViewUpdate', 'simulateDesktopViewUpdate', 'simulateDesktopControlApprovalRequest'])(
    '%s reports the trimmed chat id',
    async (name) => {
      await expect(members[name](' chat-1 ')).resolves.toEqual({ ok: true, chatId: 'chat-1' });
    },
  );
});
