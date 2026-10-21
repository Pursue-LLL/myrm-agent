/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { BreakGlassModal } from '../BreakGlassModal';
import type { BreakGlassResponse } from '@/services/sshVault';

const mockRequestBreakGlassToken = vi.hoisted(() => vi.fn());
const mockToast = vi.hoisted(() => vi.fn());

const translations: Record<string, string> = {
  breakGlassModalTitle: '受保护变更窗口破窗申请',
  readOnlyDesc: '生产级受保护隔离，拦截所有高危破坏性与写命令',
  breakGlassCommand: '变更命令',
  breakGlassReason: '变更原因',
  breakGlassReasonPlaceholder: '说明在受保护节点上执行变更的必要性与工单号...',
  breakGlassTtl: '窗口有效期 (秒)',
  breakGlassSubmit: '签发单次破窗令牌',
  breakGlassSuccess: '破窗令牌已签发并可单次执行',
  copyPrompt: '复制 Agent 调用提示词',
  copied: '已复制！',
  copyFailed: '复制失败',
  done: '完成',
  cancel: '取消',
};

const stableT = (key: string) => translations[key] || key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/services/sshVault', () => ({
  requestBreakGlassToken: (payload: unknown) => mockRequestBreakGlassToken(payload),
}));

vi.mock('@/hooks/shared/useToast', () => ({
  toast: (args: unknown) => mockToast(args),
}));

describe('BreakGlassModal', () => {
  const onClose = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });
  });

  it('renders form inputs and handles successful break-glass request', async () => {
    const mockResponse: BreakGlassResponse = {
      token: 'bg_tok_xyz123456789',
      host_alias: 'prod-db-master',
      reason: 'Urgent hotfix for ticket #402',
      expires_at: 1780000000,
    };
    mockRequestBreakGlassToken.mockResolvedValueOnce(mockResponse);

    render(<BreakGlassModal isOpen={true} onClose={onClose} hostAlias="prod-db-master" />);

    expect(screen.getByText(/受保护变更窗口破窗申请 \(prod-db-master\)/i)).toBeInTheDocument();

    const cmdInput = screen.getByLabelText(/变更命令/i);
    const reasonInput = screen.getByLabelText(/变更原因/i);
    const ttlInput = screen.getByLabelText(/窗口有效期/i);

    fireEvent.change(cmdInput, { target: { value: 'systemctl reload pgpool' } });
    fireEvent.change(reasonInput, { target: { value: 'Urgent hotfix for ticket #402' } });
    fireEvent.change(ttlInput, { target: { value: '600' } });

    const submitBtn = screen.getByRole('button', { name: /签发单次破窗令牌/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockRequestBreakGlassToken).toHaveBeenCalledWith({
        host_alias: 'prod-db-master',
        command: 'systemctl reload pgpool',
        reason: 'Urgent hotfix for ticket #402',
        ttl_seconds: 600,
      });
      expect(screen.getByText('bg_tok_xyz123456789')).toBeInTheDocument();
    });

    // Copy token
    const copyBtn = screen.getByRole('button', { name: /复制/i });
    fireEvent.click(copyBtn);
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('bg_tok_xyz123456789');
    await waitFor(() => {
      expect(screen.getByText('已复制！')).toBeInTheDocument();
    });

    // Click done to close
    const doneBtn = screen.getByRole('button', { name: /完成/i });
    fireEvent.click(doneBtn);
    expect(onClose).toHaveBeenCalled();
  });

  it('shows error toast when request fails', async () => {
    mockRequestBreakGlassToken.mockRejectedValueOnce(new Error('Permission denied'));

    render(<BreakGlassModal isOpen={true} onClose={onClose} hostAlias="prod-db-master" />);

    const cmdInput = screen.getByLabelText(/变更命令/i);
    const reasonInput = screen.getByLabelText(/变更原因/i);

    fireEvent.change(cmdInput, { target: { value: 'rm -f /tmp/lock' } });
    fireEvent.change(reasonInput, { target: { value: 'Clear stuck lock' } });

    const submitBtn = screen.getByRole('button', { name: /签发单次破窗令牌/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith(
        expect.objectContaining({
          variant: 'destructive',
          title: 'Permission denied',
        }),
      );
    });
  });

  it('calls onClose when cancel button is clicked', () => {
    render(<BreakGlassModal isOpen={true} onClose={onClose} hostAlias="prod-db-master" />);

    const cancelBtn = screen.getByRole('button', { name: /取消/i });
    fireEvent.click(cancelBtn);
    expect(onClose).toHaveBeenCalled();
  });
});
