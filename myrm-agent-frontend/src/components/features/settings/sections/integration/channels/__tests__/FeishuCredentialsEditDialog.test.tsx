/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const mockGetChannelCredentials = vi.fn();
const mockSaveChannelCredentials = vi.fn();
const mockTestFeishuConnection = vi.fn();

vi.mock('@/services/channels', async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return {
    ...actual,
    getChannelCredentials: (...args: unknown[]) => mockGetChannelCredentials(...args),
    saveChannelCredentials: (...args: unknown[]) => mockSaveChannelCredentials(...args),
    testFeishuConnection: (...args: unknown[]) => mockTestFeishuConnection(...args),
  };
});

vi.mock('@/lib/api', () => ({
  BACKEND_BASE_URL: 'http://127.0.0.1:8080',
  apiRequest: () => Promise.reject(new Error('unused in this test')),
}));

vi.mock('sonner', () => ({
  toast: {
    success: () => undefined,
    error: () => undefined,
  },
}));

import { FeishuCredentialsEditDialog } from '../FeishuCredentialsEditDialog';

describe('FeishuCredentialsEditDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetChannelCredentials.mockResolvedValue({
      appId: 'cli_existing',
      appSecret: '••••othere',
      botOpenId: 'ou_existing',
      useLark: 'false',
    });
    mockSaveChannelCredentials.mockResolvedValue({ status: 'saved', message: 'ok' });
    mockTestFeishuConnection.mockResolvedValue({ ok: true, message: 'ok' });
  });

  it('loads existing credentials when opened', async () => {
    render(<FeishuCredentialsEditDialog open onOpenChange={() => undefined} channelName="feishu_abc" />);

    await waitFor(() => {
      expect(screen.getByDisplayValue('cli_existing')).toBeInTheDocument();
      expect(screen.getByDisplayValue('ou_existing')).toBeInTheDocument();
    });
    expect(mockGetChannelCredentials).toHaveBeenCalledWith('feishu_abc');
  });

  it('saves only edited fields, keeping app secret blank to preserve current value', async () => {
    render(<FeishuCredentialsEditDialog open onOpenChange={() => undefined} channelName="feishu_abc" />);

    await waitFor(() => {
      expect(screen.getByDisplayValue('cli_existing')).toBeInTheDocument();
    });

    fireEvent.change(screen.getByDisplayValue('ou_existing'), { target: { value: 'ou_rotated' } });
    fireEvent.click(screen.getByRole('button', { name: 'feishuSave' }));

    await waitFor(() => {
      expect(mockSaveChannelCredentials).toHaveBeenCalledWith('feishu_abc', {
        appId: 'cli_existing',
        botOpenId: 'ou_rotated',
        useLark: 'false',
      });
    });
    // Blank app secret must not be submitted (backend keeps the current value).
    expect(mockSaveChannelCredentials.mock.calls[0][1].appSecret).toBeUndefined();
  });

  it('submits a new app secret when provided', async () => {
    render(<FeishuCredentialsEditDialog open onOpenChange={() => undefined} channelName="feishu_abc" />);

    await waitFor(() => {
      expect(screen.getByDisplayValue('cli_existing')).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText('feishuAppSecret'), { target: { value: 'sec_rotated' } });
    fireEvent.click(screen.getByRole('button', { name: 'feishuSave' }));

    await waitFor(() => {
      expect(mockSaveChannelCredentials).toHaveBeenCalledWith('feishu_abc', {
        appId: 'cli_existing',
        appSecret: 'sec_rotated',
        botOpenId: 'ou_existing',
        useLark: 'false',
      });
    });
  });

  it('disables save and test when app id is empty', async () => {
    mockGetChannelCredentials.mockResolvedValue({ appId: '', appSecret: '', botOpenId: '', useLark: 'false' });
    render(<FeishuCredentialsEditDialog open onOpenChange={() => undefined} channelName="feishu_abc" />);

    await waitFor(() => {
      expect(mockGetChannelCredentials).toHaveBeenCalled();
    });

    expect(screen.getByRole('button', { name: 'feishuSave' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'feishuTestConnection' })).toBeDisabled();
  });

  it('tests connection with the entered app id and secret', async () => {
    render(<FeishuCredentialsEditDialog open onOpenChange={() => undefined} channelName="feishu_abc" />);

    await waitFor(() => {
      expect(screen.getByDisplayValue('cli_existing')).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText('feishuAppSecret'), { target: { value: 'sec_rotated' } });
    fireEvent.click(screen.getByRole('button', { name: 'feishuTestConnection' }));

    await waitFor(() => {
      expect(mockTestFeishuConnection).toHaveBeenCalledWith('cli_existing', 'sec_rotated', false);
    });
  });
});
