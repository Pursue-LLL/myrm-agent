import { renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useSubmitGate } from '@/hooks/message-input/useSubmitGate';
import type { File as ChatFile } from '@/store/chat/types';

const mockValidateMessageQuota = vi.hoisted(() => vi.fn());
const toastErrorMock = vi.hoisted(() => vi.fn());
const toastWarningMock = vi.hoisted(() => vi.fn());
const storeRef = vi.hoisted(() => ({
  state: {} as { files: ChatFile[]; actionMode: string; pendingExplicitSkillActivation: unknown },
}));

vi.mock('@/hooks/billing/useQuotaGuard', () => ({
  useQuotaGuard: () => ({ validateMessageQuota: mockValidateMessageQuota }),
}));
vi.mock('@/lib/utils/toast', () => ({ toast: { error: toastErrorMock, warning: toastWarningMock } }));
vi.mock('@/store/useChatStore', () => ({ default: { getState: () => storeRef.state } }));

const UPLOAD_LIMIT_MS = 30_000;

function staged(...statuses: string[]): ChatFile[] {
  return statuses.map((status) => ({ status })) as unknown as ChatFile[];
}

function renderGate(inputMessage: string, files: ChatFile[] = []) {
  storeRef.state.files = files;
  return renderHook(() => useSubmitGate(inputMessage, files));
}

describe('useSubmitGate', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    storeRef.state = { files: [], actionMode: 'agent', pendingExplicitSkillActivation: null };
    mockValidateMessageQuota.mockReset();
    mockValidateMessageQuota.mockResolvedValue({ allowed: true });
    toastErrorMock.mockReset();
    toastWarningMock.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('lets a message with text through and asks the quota guard about its size and the live action mode', async () => {
    const { result } = renderGate('  hello  ');
    storeRef.state.actionMode = 'deep_research';

    await expect(result.current()).resolves.toBe(true);

    expect(mockValidateMessageQuota).toHaveBeenCalledWith(5, false, 'deep_research');
  });

  it('holds back an empty message', async () => {
    const { result } = renderGate('   ');

    await expect(result.current()).resolves.toBe(false);

    expect(mockValidateMessageQuota).not.toHaveBeenCalled();
  });

  it('lets an empty message through when a skill is waiting to be activated with it', async () => {
    storeRef.state.pendingExplicitSkillActivation = { skillId: 'pdf' };
    const { result } = renderGate('');

    await expect(result.current()).resolves.toBe(true);
  });

  it('lets an attachment go out without any text and tells the guard it has one', async () => {
    const { result } = renderGate('', staged('done'));

    await expect(result.current()).resolves.toBe(true);

    expect(mockValidateMessageQuota).toHaveBeenCalledWith(0, true, 'agent');
  });

  it('holds back a message the quota guard refuses', async () => {
    mockValidateMessageQuota.mockResolvedValue({ allowed: false, reason: 'wu_limit' });
    const { result } = renderGate('hello');

    await expect(result.current()).resolves.toBe(false);
  });

  describe('attachments that are still uploading', () => {
    it('waits for them to finish, then lets the message through', async () => {
      const files = staged('uploading');
      const { result } = renderGate('look at this', files);
      const gate = result.current();

      await vi.advanceTimersByTimeAsync(300);
      expect(mockValidateMessageQuota).not.toHaveBeenCalled();
      storeRef.state.files = staged('done');
      await vi.advanceTimersByTimeAsync(100);

      await expect(gate).resolves.toBe(true);
      expect(mockValidateMessageQuota).toHaveBeenCalledTimes(1);
    });

    it('holds the message back and says so when an upload ended in an error', async () => {
      const { result } = renderGate('look at this', staged('uploading'));
      const gate = result.current();

      storeRef.state.files = staged('error');
      await vi.advanceTimersByTimeAsync(100);

      await expect(gate).resolves.toBe(false);
      expect(toastErrorMock).toHaveBeenCalledWith('uploadFailed');
      expect(mockValidateMessageQuota).not.toHaveBeenCalled();
    });

    it('holds the message back and says so when an upload is still running after thirty seconds', async () => {
      const { result } = renderGate('look at this', staged('uploading'));
      const gate = result.current();

      await vi.advanceTimersByTimeAsync(UPLOAD_LIMIT_MS + 100);

      await expect(gate).resolves.toBe(false);
      expect(toastWarningMock).toHaveBeenCalledWith('uploadPending');
      expect(toastErrorMock).not.toHaveBeenCalled();
      expect(mockValidateMessageQuota).not.toHaveBeenCalled();
    });

    it('reports a failed upload rather than a pending one when both are present at the deadline', async () => {
      const { result } = renderGate('look at this', staged('uploading', 'error'));
      const gate = result.current();

      await vi.advanceTimersByTimeAsync(UPLOAD_LIMIT_MS + 100);

      await expect(gate).resolves.toBe(false);
      expect(toastErrorMock).toHaveBeenCalledWith('uploadFailed');
      expect(toastWarningMock).not.toHaveBeenCalled();
    });
  });

  it('holds the message back when an attachment already failed to upload, even with nothing left uploading', async () => {
    const { result } = renderGate('look at this', staged('ready', 'error'));

    await expect(result.current()).resolves.toBe(false);

    expect(toastErrorMock).toHaveBeenCalledWith('uploadFailed');
    expect(mockValidateMessageQuota).not.toHaveBeenCalled();
  });
});
