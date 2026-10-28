'use client';

/**
 * A command approval can carry a one-time password or key. It is staged for the exact command on the card, goes
 * with the approval unchanged, and is destroyed when the person rejects, rewrites the command, or lets it expire.
 */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import SingleApprovalCard from '@/components/features/chat-window/SingleApprovalCard';
import type { ToolApprovalRequest } from '@/store/chat/types';

const stableT = (key: string, values?: Record<string, unknown>) => (values ? `${key}:${JSON.stringify(values)}` : key);

vi.mock('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: () => stableT,
}));

const toastMock = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() }));
vi.mock('sonner', () => ({ toast: toastMock }));
vi.mock('@/lib/utils/toast', () => ({ toast: toastMock }));

const client = vi.hoisted(() => ({
  stageOneTimeCredentials: vi.fn(),
  wipeOneTimeCredentials: vi.fn(),
}));
vi.mock('@/lib/approval/oneTimeCredentials', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/approval/oneTimeCredentials')>()),
  ...client,
}));

vi.mock('@/store/useDesktopInspectorStore', () => ({
  default: (selector: (state: { viewData: null }) => unknown) => selector({ viewData: null }),
  selectScopedDesktopViewData: () => null,
}));

vi.mock('@/store/useBrowserInspectorStore', () => ({
  default: (selector: (state: { viewData: null }) => unknown) => selector({ viewData: null }),
  selectScopedBrowserViewData: () => null,
}));

const COMMAND = 'psql -h db.internal -U app -c "select 1"';

function buildRequest(overrides: Partial<ToolApprovalRequest> = {}): ToolApprovalRequest {
  return {
    requestId: 'req-bash',
    toolName: 'bash_code_execute_tool',
    toolInput: { command: COMMAND },
    reason: '',
    timeoutSeconds: 60,
    expiresAt: Math.floor(Date.now() / 1000) + 60,
    timeoutBehavior: 'deny',
    messageId: 'msg-1',
    displayMode: 'approval',
    chatId: 'chat-1',
    actionMode: 'agent',
    ...overrides,
  };
}

function renderCard(request: ToolApprovalRequest) {
  const onResolve = vi.fn(async () => {});
  render(<SingleApprovalCard request={request} onResolve={onResolve} isLoading={false} />);
  return onResolve;
}

async function stageCredential() {
  fireEvent.click(screen.getByRole('button', { name: /^open/ }));
  fireEvent.change(screen.getByPlaceholderText('API_SECRET_KEY'), { target: { value: 'PGPASSWORD' } });
  fireEvent.change(screen.getByPlaceholderText('••••••••••••'), { target: { value: 'hunter2' } });
  fireEvent.click(screen.getByText('stage'));
  await waitFor(() => expect(screen.getByText('stagedReady')).toBeDefined());
}

describe('SingleApprovalCard one-time credentials', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    client.stageOneTimeCredentials.mockResolvedValue([{ handleId: 'h1', key: 'PGPASSWORD' }]);
    client.wipeOneTimeCredentials.mockResolvedValue(undefined);
  });

  it('offers the entry on a bash command approval', () => {
    renderCard(buildRequest());

    expect(screen.getByRole('button', { name: /^open/ })).toBeDefined();
  });

  it.each([
    ['another tool', { toolName: 'file_read_tool', toolInput: { paths: ['/a'] } }],
    ['a script tool without the bash executor', { toolName: 'execute_code', toolInput: { code: 'print(1)' } }],
    ['a command the policy refused', { smartDenied: true }],
  ])('offers nothing for %s', (_label, overrides) => {
    renderCard(buildRequest(overrides as Partial<ToolApprovalRequest>));

    expect(screen.queryByRole('button', { name: /^open/ })).toBeNull();
  });

  it('stages for this chat and the command exactly as shown', async () => {
    renderCard(buildRequest());

    await stageCredential();

    expect(client.stageOneTimeCredentials).toHaveBeenCalledWith('chat-1', COMMAND, [
      { key: 'PGPASSWORD', secret: 'hunter2', ttlSeconds: 60 },
    ]);
    expect(screen.getByRole('button', { name: /^readyCount/ })).toBeDefined();
  });

  it('approving sends no credential with the decision and keeps it for the command to read', async () => {
    const onResolve = renderCard(buildRequest());
    await stageCredential();

    fireEvent.click(screen.getByRole('button', { name: 'approve' }));

    expect(onResolve).toHaveBeenCalledWith('req-bash', 'approve', {});
    expect(JSON.stringify(onResolve.mock.calls)).not.toContain('hunter2');
    expect(client.wipeOneTimeCredentials).not.toHaveBeenCalled();
  });

  it('rejecting destroys what was staged', async () => {
    const onResolve = renderCard(buildRequest());
    await stageCredential();

    fireEvent.click(screen.getByRole('button', { name: 'reject' }));
    fireEvent.click(screen.getByRole('button', { name: 'confirmReject' }));

    await waitFor(() => expect(onResolve).toHaveBeenCalledWith('req-bash', 'reject', { feedback: undefined }));
    expect(client.wipeOneTimeCredentials).toHaveBeenCalledWith('chat-1', ['h1']);
  });

  it('keeps what was staged when the person only looks at the edit view and cancels', async () => {
    renderCard(buildRequest());
    await stageCredential();

    fireEvent.click(screen.getByRole('button', { name: 'edit' }));
    fireEvent.click(screen.getByRole('button', { name: 'cancel' }));

    expect(client.wipeOneTimeCredentials).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: /^readyCount/ })).toBeDefined();
  });

  it('destroys what was staged when the command is rewritten, and says so', async () => {
    const onResolve = renderCard(buildRequest());
    await stageCredential();

    fireEvent.click(screen.getByRole('button', { name: 'edit' }));
    fireEvent.change(screen.getByRole('textbox'), { target: { value: `${COMMAND} -x` } });
    fireEvent.click(screen.getByRole('button', { name: 'confirmEdit' }));

    await waitFor(() => expect(onResolve).toHaveBeenCalledWith('req-bash', 'edit', expect.anything()));
    expect(client.wipeOneTimeCredentials).toHaveBeenCalledWith('chat-1', ['h1']);
    expect(toastMock.info).toHaveBeenCalledWith('maskedCredentials.droppedOnEdit');
  });

  it('keeps what was staged when the edit leaves the command as it was', async () => {
    const onResolve = renderCard(buildRequest());
    await stageCredential();

    fireEvent.click(screen.getByRole('button', { name: 'edit' }));
    fireEvent.click(screen.getByRole('button', { name: 'confirmEdit' }));

    await waitFor(() => expect(onResolve).toHaveBeenCalledWith('req-bash', 'approve', expect.anything()));
    expect(client.wipeOneTimeCredentials).not.toHaveBeenCalled();
  });

  it('destroys what was staged and warns when it expires before the person decides', async () => {
    vi.useFakeTimers();
    try {
      renderCard(buildRequest());
      fireEvent.click(screen.getByRole('button', { name: /^open/ }));
      fireEvent.change(screen.getByPlaceholderText('API_SECRET_KEY'), { target: { value: 'PGPASSWORD' } });
      fireEvent.change(screen.getByPlaceholderText('••••••••••••'), { target: { value: 'hunter2' } });
      fireEvent.change(screen.getByRole('combobox'), { target: { value: '30' } });
      await act(async () => {
        fireEvent.click(screen.getByText('stage'));
      });

      await act(async () => {
        vi.advanceTimersByTime(30_000);
      });

      expect(client.wipeOneTimeCredentials).toHaveBeenCalledWith('chat-1', ['h1']);
      expect(toastMock.warning).toHaveBeenCalledWith('maskedCredentials.toastExpired');
      expect(screen.getByRole('button', { name: /^open/ })).toBeDefined();
    } finally {
      vi.useRealTimers();
    }
  });
});
