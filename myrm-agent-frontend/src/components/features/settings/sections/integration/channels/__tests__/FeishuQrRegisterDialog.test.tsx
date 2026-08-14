/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const mockApiRequest = vi.fn();

vi.mock('@/lib/api', () => ({
  BACKEND_BASE_URL: 'http://127.0.0.1:8080',
  apiRequest: (...args: unknown[]) => mockApiRequest(...args),
}));

vi.mock('qrcode.react', () => ({
  QRCodeSVG: () => null,
}));

import { FeishuQrRegisterDialog } from '../FeishuQrRegisterDialog';

const POLL_SUCCESS = {
  status: 'success',
  credentials: { appId: 'cli_1', appSecret: 'sec_1', useLark: 'false', botOpenId: 'ou_1' },
  instance_id: 'inst1',
  channel_name: 'feishu_inst1',
};

describe('FeishuQrRegisterDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApiRequest.mockReset();
  });

  it('requires a label in multi-app mode before scanning', () => {
    render(<FeishuQrRegisterDialog open onOpenChange={() => undefined} allowLabel />);

    expect(screen.getByRole('button', { name: 'feishuScanToAdd' })).toBeDisabled();
    expect(screen.getByText('feishuAppLabelRequired')).toBeInTheDocument();
  });

  it('enables scanning once a label is provided', () => {
    render(<FeishuQrRegisterDialog open onOpenChange={() => undefined} allowLabel />);

    fireEvent.change(screen.getByLabelText('feishuAppLabelPlaceholder'), { target: { value: 'Support' } });

    expect(screen.getByRole('button', { name: 'feishuScanToAdd' })).toBeEnabled();
    expect(screen.queryByText('feishuAppLabelRequired')).not.toBeInTheDocument();
  });

  it('does not require a label in default-instance refresh mode', () => {
    render(<FeishuQrRegisterDialog open onOpenChange={() => undefined} />);

    expect(screen.getByRole('button', { name: 'feishuQrButton' })).toBeEnabled();
    expect(screen.queryByText('feishuAppLabelRequired')).not.toBeInTheDocument();
  });

  it('runs the scan flow and reports success with instance metadata', async () => {
    mockApiRequest
      .mockResolvedValueOnce({ session_id: 's1', qr_url: 'https://feishu.cn/qr', expire_in: 300, interval: 0.05 })
      .mockResolvedValue(POLL_SUCCESS);
    const onSuccess = vi.fn();
    const onOpenChange = vi.fn();

    render(<FeishuQrRegisterDialog open onOpenChange={onOpenChange} allowLabel onSuccess={onSuccess} />);
    fireEvent.change(screen.getByLabelText('feishuAppLabelPlaceholder'), { target: { value: 'Support' } });
    fireEvent.click(screen.getByRole('button', { name: 'feishuScanToAdd' }));

    await waitFor(() => {
      expect(mockApiRequest).toHaveBeenCalledTimes(1);
    });
    expect(screen.getByText('feishuQrScanHint')).toBeInTheDocument();

    await waitFor(
      () => {
        expect(onSuccess).toHaveBeenCalledWith({ instanceId: 'inst1', channelName: 'feishu_inst1' });
        expect(onOpenChange).toHaveBeenCalledWith(false);
      },
      { timeout: 5000 },
    );
  });

  it('shows failed status when the scan is denied', async () => {
    mockApiRequest
      .mockResolvedValueOnce({ session_id: 's1', qr_url: 'https://feishu.cn/qr', expire_in: 300, interval: 0.05 })
      .mockResolvedValue({ status: 'denied', credentials: null });
    const onSuccess = vi.fn();

    render(<FeishuQrRegisterDialog open onOpenChange={() => undefined} onSuccess={onSuccess} />);
    fireEvent.click(screen.getByRole('button', { name: 'feishuQrButton' }));

    await waitFor(
      () => {
        expect(screen.getByText('feishuQrFailed')).toBeInTheDocument();
      },
      { timeout: 3000 },
    );
    expect(onSuccess).not.toHaveBeenCalled();
  });
});
