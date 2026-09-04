/** @vitest-environment jsdom */

/**
 * [INPUT] @/components/features/sidebar/CaptureEvalCaseDialog, @/services/eval
 * [OUTPUT] CaptureEvalCaseDialog 单元测试：覆盖数据集拉取、切换新建、确认提交与状态流转
 * [POS] sidebar/__tests__ 测试套件
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const mockToast = vi.fn();
vi.mock('@/hooks/shared/useToast', () => ({
  useToast: () => ({ toast: mockToast }),
}));

const mockGetDatasets = vi.fn();
const mockCaptureCaseFromChat = vi.fn();

vi.mock('@/services/eval', () => ({
  evalService: {
    getDatasets: () => mockGetDatasets(),
    captureCaseFromChat: (...args: unknown[]) => mockCaptureCaseFromChat(...args),
  },
}));

import { CaptureEvalCaseDialog } from '../CaptureEvalCaseDialog';

describe('CaptureEvalCaseDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetDatasets.mockResolvedValue({
      datasets: [
        { id: 'default', name: 'default', count: 5 },
        { id: 'crawler-tests', name: 'crawler-tests', count: 2 },
      ],
    });
    mockCaptureCaseFromChat.mockResolvedValue({ status: 'success' });
  });

  it('renders dataset selector when opened and loads datasets', async () => {
    const onOpenChange = vi.fn();
    render(
      <CaptureEvalCaseDialog
        open={true}
        onOpenChange={onOpenChange}
        chatId="chat-123"
      />,
    );

    expect(screen.getByText('chat.captureEvalCase.title')).toBeInTheDocument();
    expect(screen.getByText('chat.captureEvalCase.description')).toBeInTheDocument();

    await waitFor(() => {
      expect(mockGetDatasets).toHaveBeenCalledTimes(1);
      expect(screen.getByText('default (5)')).toBeInTheDocument();
      expect(screen.getByText('crawler-tests (2)')).toBeInTheDocument();
    });
  });

  it('submits with existing dataset successfully', async () => {
    const onOpenChange = vi.fn();
    const onSuccess = vi.fn();

    render(
      <CaptureEvalCaseDialog
        open={true}
        onOpenChange={onOpenChange}
        chatId="chat-123"
        onSuccess={onSuccess}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText('default (5)')).toBeInTheDocument();
    });

    const confirmBtn = screen.getByRole('button', { name: 'chat.captureEvalCase.confirm' });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(mockCaptureCaseFromChat).toHaveBeenCalledWith('chat-123', 'default');
      expect(onOpenChange).toHaveBeenCalledWith(false);
      expect(onSuccess).toHaveBeenCalledTimes(1);
      expect(mockToast).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'chat.captureEvalCase.success',
        }),
      );
    });
  });

  it('allows switching to new dataset creation and submitting', async () => {
    const onOpenChange = vi.fn();

    render(
      <CaptureEvalCaseDialog
        open={true}
        onOpenChange={onOpenChange}
        chatId="chat-123"
      />,
    );

    await waitFor(() => {
      expect(screen.getByText('default (5)')).toBeInTheDocument();
    });

    const newBtn = screen.getByRole('button', { name: 'chat.captureEvalCase.newDataset' });
    fireEvent.click(newBtn);

    const input = screen.getByPlaceholderText('chat.captureEvalCase.newDatasetPlaceholder');
    expect(input).toBeInTheDocument();

    fireEvent.change(input, { target: { value: 'finance-regressions' } });

    const confirmBtn = screen.getByRole('button', { name: 'chat.captureEvalCase.confirm' });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(mockCaptureCaseFromChat).toHaveBeenCalledWith('chat-123', 'finance-regressions');
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
  });

  it('validates empty dataset name when creating new dataset', async () => {
    const onOpenChange = vi.fn();

    render(
      <CaptureEvalCaseDialog
        open={true}
        onOpenChange={onOpenChange}
        chatId="chat-123"
      />,
    );

    await waitFor(() => {
      expect(screen.getByText('default (5)')).toBeInTheDocument();
    });

    const newBtn = screen.getByRole('button', { name: 'chat.captureEvalCase.newDataset' });
    fireEvent.click(newBtn);

    const input = screen.getByPlaceholderText('chat.captureEvalCase.newDatasetPlaceholder');
    fireEvent.change(input, { target: { value: '   ' } });

    const confirmBtn = screen.getByRole('button', { name: 'chat.captureEvalCase.confirm' });
    fireEvent.click(confirmBtn);

    expect(mockCaptureCaseFromChat).not.toHaveBeenCalled();
    expect(mockToast).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'chat.captureEvalCase.error',
        variant: 'destructive',
      }),
    );
  });
});
