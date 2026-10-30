/**
 * Bringing back the approval card of a parked chat while the shared approval queue already holds cards of other chats.
 *
 * Real scenario: after a reload, chats A and B both wait behind a tool-approval card. The user opens A (its card comes
 * back), then opens B: B's card has to come back too, although the queue is no longer empty.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fetchWithTimeout } from '@/lib/api';
import { resolveE2eApiBase } from '@/lib/deploy-mode';
import { attachForHitlRecovery, type ChatActionsMethods } from '@/store/chat/messageRequest';
import type { Message, ToolApprovalRequest } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';
import useToolApprovalStore from '@/store/useToolApprovalStore';

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, fetchWithTimeout: vi.fn() };
});

vi.mock('@/lib/deploy-mode', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/deploy-mode')>();
  return { ...actual, resolveE2eApiBase: vi.fn(() => '') };
});

vi.mock('@/hooks/approval/usePendingApprovalsRecovery', () => ({
  recoverPendingApprovals: vi.fn(),
}));

vi.mock('@/lib/approval/approvalAlertService', () => ({
  notifyIdleApproval: vi.fn(),
}));

const CHAT_A = 'chat-a';
const CHAT_B = 'chat-b';

function queuedCard(chatId: string): ToolApprovalRequest {
  return {
    requestId: `req-${chatId}`,
    toolName: 'bash_code_execute_tool',
    toolInput: { command: 'curl x' },
    reason: 'asks',
    timeoutSeconds: 600,
    expiresAt: Date.now() + 600_000,
    timeoutBehavior: 'deny',
    messageId: `msg-${chatId}`,
    displayMode: 'approval',
    chatId,
    actionMode: 'agent',
    interruptId: `int-${chatId}`,
  };
}

function snapshotEvent(chatId: string) {
  return {
    type: 'catchup_snapshot',
    messageId: `msg-${chatId}`,
    data: { content: '', reasoning: '', progress_steps: [], sources: [] },
  };
}

function approvalEvent(chatId: string) {
  return {
    type: 'tool_approval_request',
    messageId: `msg-${chatId}`,
    interruptId: `int-${chatId}`,
    data: {
      actionRequests: [{ action: 'bash_code_execute_tool', args: { command: 'curl x' }, description: 'run' }],
      reviewConfigs: [{}],
      extensions: { approval: { requestId: `req-${chatId}` } },
    },
  };
}

/** What a parked collector sends to an attach: the snapshot, then the card it still holds; the stream stays open after that. */
function parkedCollectorStream(chatId: string): Response {
  const body = [snapshotEvent(chatId), approvalEvent(chatId)]
    .map((event) => `data: ${JSON.stringify(event)}\n\n`)
    .join('');
  return new Response(
    new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(body));
      },
    }),
    { headers: { 'Content-Type': 'text/event-stream' } },
  );
}

const actions = {
  setMessages: (updater: Parameters<ChatActionsMethods['setMessages']>[0]) => useChatStore.setState(updater),
  setMessageAppeared: vi.fn(),
  setLoading: vi.fn(),
  setInputMessage: vi.fn(),
  clearActiveStream: vi.fn(),
  _processSuggestions: vi.fn(),
  scheduleAutoSave: vi.fn(),
} as unknown as ChatActionsMethods;

function queuedChats(): string[] {
  return useToolApprovalStore.getState().queue.map((request) => request.chatId);
}

describe('attachForHitlRecovery with approval cards of other chats in the queue', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useToolApprovalStore.getState().clearAll();
    useChatStore.setState({
      chatId: CHAT_B,
      loading: false,
      messages: [
        {
          messageId: `msg-${CHAT_B}`,
          chatId: CHAT_B,
          role: 'assistant',
          content: '',
          createdAt: new Date(),
        } as Message,
      ],
    });
  });

  it("brings the chat's own card back although another chat's card is already queued", async () => {
    useToolApprovalStore.getState().addRequest(queuedCard(CHAT_A));
    vi.mocked(fetchWithTimeout).mockResolvedValue(parkedCollectorStream(CHAT_B));

    const result = await attachForHitlRecovery(CHAT_B, actions, useChatStore.getState);

    expect(fetchWithTimeout).toHaveBeenCalledTimes(1);
    expect(vi.mocked(fetchWithTimeout).mock.calls[0]?.[0]).toBe(`/agents/chat/${CHAT_B}/attach`);
    expect(queuedChats()).toEqual([CHAT_A, CHAT_B]);
    expect(result).toMatchObject({ attached: true, queueLen: 1, source: 'attach' });
  });

  it('leaves the queue alone when the chat already has its card queued', async () => {
    useToolApprovalStore.getState().addRequest(queuedCard(CHAT_A));
    useToolApprovalStore.getState().addRequest(queuedCard(CHAT_B));

    const result = await attachForHitlRecovery(CHAT_B, actions, useChatStore.getState);

    expect(fetchWithTimeout).not.toHaveBeenCalled();
    expect(queuedChats()).toEqual([CHAT_A, CHAT_B]);
    expect(result).toMatchObject({ attached: true, queueLen: 1, source: 'attach' });
  });

  it("does not report a restore because of another chat's card when the server has nothing parked for this chat", async () => {
    useToolApprovalStore.getState().addRequest(queuedCard(CHAT_A));
    vi.mocked(fetchWithTimeout).mockResolvedValue(new Response(null, { status: 404 }));

    const result = await attachForHitlRecovery(CHAT_B, actions, useChatStore.getState);

    expect(queuedChats()).toEqual([CHAT_A]);
    expect(result).toMatchObject({ attached: false, queueLen: 0, source: 'none' });
  });

  describe('E2E probe fallback', () => {
    beforeEach(() => {
      vi.mocked(resolveE2eApiBase).mockReturnValue('http://e2e.test');
    });

    it("replays the chat's own parked card from the probe although another chat's card is already queued", async () => {
      useToolApprovalStore.getState().addRequest(queuedCard(CHAT_A));
      const attachWithoutCard = new Response(`data: ${JSON.stringify(snapshotEvent(CHAT_B))}\n\n`, {
        headers: { 'Content-Type': 'text/event-stream' },
      });
      const probe = Response.json({ pending_interrupt_events: [snapshotEvent(CHAT_B), approvalEvent(CHAT_B)] });
      vi.mocked(fetchWithTimeout).mockResolvedValueOnce(attachWithoutCard).mockResolvedValueOnce(probe);

      const result = await attachForHitlRecovery(CHAT_B, actions, useChatStore.getState);

      expect(queuedChats()).toEqual([CHAT_A, CHAT_B]);
      expect(result).toMatchObject({ attached: true, queueLen: 1, source: 'probe' });
    });

    it("counts only this chat's cards when the probe has nothing for it", async () => {
      useToolApprovalStore.getState().addRequest(queuedCard(CHAT_A));
      const attachWithoutCard = new Response(`data: ${JSON.stringify(snapshotEvent(CHAT_B))}\n\n`, {
        headers: { 'Content-Type': 'text/event-stream' },
      });
      const emptyProbe = Response.json({ pending_interrupt_events: [] });
      vi.mocked(fetchWithTimeout).mockResolvedValueOnce(attachWithoutCard).mockResolvedValueOnce(emptyProbe);

      const result = await attachForHitlRecovery(CHAT_B, actions, useChatStore.getState);

      expect(queuedChats()).toEqual([CHAT_A]);
      expect(result).toMatchObject({ attached: false, queueLen: 0, source: 'none' });
    });
  });
});
