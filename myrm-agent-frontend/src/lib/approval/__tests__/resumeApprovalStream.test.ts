import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AgentBusyError, ApprovalExpiredError } from '@/store/chat/streamErrors';
import type { ToolApprovalRequest } from '@/store/chat/types/toolApproval';

const mockCreateAISearchStream = vi.hoisted(() => vi.fn());
const mockHandleMessageStream = vi.hoisted(() => vi.fn());
const mockGetModelSelection = vi.hoisted(() => vi.fn());

vi.mock('@/services/chat', () => ({
  createAISearchStream: (...args: unknown[]) => mockCreateAISearchStream(...args),
}));

vi.mock('@/store/chat/messageStreamHandler', () => ({
  handleMessageStream: (...args: unknown[]) => mockHandleMessageStream(...args),
}));

vi.mock('@/store/chat/messageRequest', () => ({
  getModelSelection: (...args: unknown[]) => mockGetModelSelection(...args),
  getLiteModelSelection: () => null,
  getFallbackModelSelection: () => null,
  getFallbackLiteModelSelection: () => null,
}));

vi.mock('@/store/useChatStore', () => ({
  default: {
    getState: () => ({
      actionMode: 'agent',
      agentConfig: null,
      abortController: null,
      messages: [],
      messageAppeared: false,
      loading: false,
      setMessageAppeared: vi.fn(),
      setLoading: vi.fn(),
      _processSuggestions: vi.fn(),
      scheduleAutoSave: vi.fn(),
    }),
    setState: vi.fn(),
  },
}));

function buildRequest(): ToolApprovalRequest {
  return {
    requestId: 'req-1',
    toolName: 'bash',
    toolInput: {},
    reason: 'test',
    timeoutSeconds: 300,
    expiresAt: Math.floor(Date.now() / 1000) + 300,
    timeoutBehavior: 'deny',
    messageId: 'msg-approval-1',
    displayMode: 'approval',
    chatId: 'chat-1',
    actionMode: 'agent',
  };
}

function conflictResponse(): Response {
  return new Response(JSON.stringify({ detail: 'This approval has already been resolved by timeout.' }), {
    status: 409,
    headers: { 'Content-Type': 'application/json' },
  });
}

function sseBusyResponse(): Response {
  const body = 'data: {"type":"error","error_type":"AgentBusyError","status_code":409}\n\n';
  return new Response(body, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  });
}

describe('resumeApprovalStream', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetModelSelection.mockReturnValue({ providerId: 'openai', model: 'test-model' });
    mockHandleMessageStream.mockResolvedValue({ added: false, recievedMessage: '' });
  });

  it('throws AgentBusyError on HTTP 200 SSE AgentBusyError envelope', async () => {
    mockCreateAISearchStream.mockResolvedValue(sseBusyResponse());

    const { resumeApprovalStream } = await import('../resumeApprovalStream');

    await expect(resumeApprovalStream(buildRequest(), { decision: 'approve' }, 'resume failed')).rejects.toBeInstanceOf(
      AgentBusyError,
    );

    expect(mockHandleMessageStream).not.toHaveBeenCalled();
  });

  it('throws ApprovalExpiredError when the timeout already answered the approval (HTTP 409)', async () => {
    mockCreateAISearchStream.mockResolvedValue(conflictResponse());

    const { resumeApprovalStream } = await import('../resumeApprovalStream');

    await expect(resumeApprovalStream(buildRequest(), { decision: 'approve' }, 'resume failed')).rejects.toBeInstanceOf(
      ApprovalExpiredError,
    );

    expect(mockHandleMessageStream).not.toHaveBeenCalled();
  });

  it('keeps other HTTP failures as plain errors', async () => {
    mockCreateAISearchStream.mockResolvedValue(new Response('boom', { status: 500 }));

    const { resumeApprovalStream } = await import('../resumeApprovalStream');

    const failure = resumeApprovalStream(buildRequest(), { decision: 'approve' }, 'resume failed');
    await expect(failure).rejects.toThrow('Approval resume failed: HTTP 500');
    await expect(failure).rejects.not.toBeInstanceOf(ApprovalExpiredError);
  });
});
