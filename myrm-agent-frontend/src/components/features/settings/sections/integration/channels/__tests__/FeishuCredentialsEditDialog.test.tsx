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
      useLark: 'false',
    });
    mockSaveChannelCredentials.mockResolvedValue({ status: 'saved', message: 'ok' });
    mockTestFeishuConnection.mockResolvedValue({ ok: true, message: 'ok' });
  });

  it('loads existing credentials when opened', async () => {
    render(<FeishuCredentialsEditDialog open onOpenChange={() => undefined} channelName="feishu_abc" />);

    await waitFor(() => {
      expect(screen.getByDisplayValue('cli_existing')).toBeInTheDocument();
    });
    expect(mockGetChannelCredentials).toHaveBeenCalledWith('feishu_abc');
  });

  it('saves only edited fields, keeping app secret blank to preserve current value', async () => {
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
        useLark: 'false',
      });
    });
  });

  it('does not submit a blank app secret', async () => {
    render(<FeishuCredentialsEditDialog open onOpenChange={() => undefined} channelName="feishu_abc" />);

    await waitFor(() => {
      expect(screen.getByDisplayValue('cli_existing')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'feishuSave' }));

    await waitFor(() => {
      expect(mockSaveChannelCredentials).toHaveBeenCalledWith('feishu_abc', {
        appId: 'cli_existing',
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
        useLark: 'false',
      });
    });
  });

  it('disables save and test when app id is empty', async () => {
    mockGetChannelCredentials.mockResolvedValue({ appId: '', appSecret: '', useLark: 'false' });
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

  it('reloads credentials each time the dialog is opened with the same channel', async () => {
    const { rerender } = render(
      <FeishuCredentialsEditDialog open={false} onOpenChange={() => undefined} channelName="feishu_abc" />,
    );
    expect(mockGetChannelCredentials).not.toHaveBeenCalled();

    rerender(<FeishuCredentialsEditDialog open onOpenChange={() => undefined} channelName="feishu_abc" />);
    await waitFor(() => {
      expect(mockGetChannelCredentials).toHaveBeenCalledTimes(1);
      expect(screen.getByDisplayValue('cli_existing')).toBeInTheDocument();
    });

    // Close and reopen the same instance: the form must be refetched, not left blank.
    rerender(<FeishuCredentialsEditDialog open={false} onOpenChange={() => undefined} channelName="feishu_abc" />);
    mockGetChannelCredentials.mockClear();
    rerender(<FeishuCredentialsEditDialog open onOpenChange={() => undefined} channelName="feishu_abc" />);

    await waitFor(() => {
      expect(mockGetChannelCredentials).toHaveBeenCalledTimes(1);
      expect(mockGetChannelCredentials).toHaveBeenCalledWith('feishu_abc');
      expect(screen.getByDisplayValue('cli_existing')).toBeInTheDocument();
    });
  });

  it('ignores a stale load when the dialog is re-opened for another instance', async () => {
    let resolveFirst: (value: unknown) => void;
    const pendingFirst = new Promise((resolve) => {
      resolveFirst = resolve;
    });
    mockGetChannelCredentials.mockReturnValueOnce(pendingFirst);
    mockGetChannelCredentials.mockResolvedValue({ appId: 'cli_second', useLark: 'true' });

    const { rerender } = render(
      <FeishuCredentialsEditDialog open onOpenChange={() => undefined} channelName="feishu_abc" />,
    );

    // Re-open for a different instance while the first request is in flight.
    rerender(<FeishuCredentialsEditDialog open={false} onOpenChange={() => undefined} channelName="feishu_abc" />);
    rerender(<FeishuCredentialsEditDialog open onOpenChange={() => undefined} channelName="feishu_second" />);

    await waitFor(() => {
      expect(mockGetChannelCredentials).toHaveBeenCalledTimes(2);
    });

    // Resolve the stale first request late; it must not overwrite the form.
    resolveFirst!({ appId: 'cli_stale', useLark: 'false' });
    await new Promise((r) => setTimeout(r, 0));

    expect(screen.getByDisplayValue('cli_second')).toBeInTheDocument();
    expect(screen.queryByDisplayValue('cli_stale')).not.toBeInTheDocument();
  });
});
