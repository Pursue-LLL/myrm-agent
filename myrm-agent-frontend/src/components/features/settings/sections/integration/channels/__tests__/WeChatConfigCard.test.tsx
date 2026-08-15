/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const mockGetWeChatStatus = vi.fn();
const mockLogoutWeChatChannel = vi.fn();
const mockListChannelInstances = vi.fn();
const mockDeleteChannelInstance = vi.fn();
const mockCreateChannelInstance = vi.fn();
const mockUpdateChannelDisplayName = vi.fn();

vi.mock('@/services/channels', async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return {
    ...actual,
    getWeChatStatus: (...args: unknown[]) => mockGetWeChatStatus(...args),
    logoutWeChatChannel: (...args: unknown[]) => mockLogoutWeChatChannel(...args),
    listChannelInstances: (...args: unknown[]) => mockListChannelInstances(...args),
    deleteChannelInstance: (...args: unknown[]) => mockDeleteChannelInstance(...args),
    createChannelInstance: (...args: unknown[]) => mockCreateChannelInstance(...args),
    updateChannelDisplayName: (...args: unknown[]) => mockUpdateChannelDisplayName(...args),
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

import { WeChatConfigCard } from '../WeChatConfigCard';

describe('WeChatConfigCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetWeChatStatus.mockResolvedValue({
      connected: true,
      qr_code: null,
      bot_id: 'wxid_demo',
      status: 'running',
    });
    mockListChannelInstances.mockResolvedValue([]);
    mockLogoutWeChatChannel.mockResolvedValue({ status: 'stopped' });
    mockDeleteChannelInstance.mockResolvedValue(undefined);
    mockUpdateChannelDisplayName.mockResolvedValue({ displayName: 'renamed' });
  });

  it('logs out the primary WeChat account after confirming', async () => {
    render(<WeChatConfigCard />);
    await waitFor(() => {
      expect(screen.getByLabelText('delete-wechat')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText('delete-wechat'));
    await waitFor(() => {
      expect(screen.getByText('channelDeleteInstanceTitle')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'channelDeleteInstanceConfirm' }));
    await waitFor(() => {
      expect(mockLogoutWeChatChannel).toHaveBeenCalledWith('wechat');
    });
  });

  it('keeps the primary account when logout confirmation is cancelled', async () => {
    render(<WeChatConfigCard />);
    await waitFor(() => {
      expect(screen.getByLabelText('delete-wechat')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText('delete-wechat'));
    await waitFor(() => {
      expect(screen.getByText('channelDeleteInstanceTitle')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'channelDeleteInstanceCancel' }));
    await waitFor(() => {
      expect(screen.queryByText('channelDeleteInstanceTitle')).not.toBeInTheDocument();
    });
    expect(mockLogoutWeChatChannel).not.toHaveBeenCalled();
  });

  it('deletes an extra instance after confirming', async () => {
    mockListChannelInstances.mockResolvedValue([
      {
        instanceId: 'inst1',
        channelType: 'wechat',
        channelName: 'wechat_inst1',
        displayName: '客服微信',
      },
    ]);

    render(<WeChatConfigCard />);
    await waitFor(() => {
      expect(screen.getByLabelText('delete-wechat_inst1')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText('delete-wechat_inst1'));
    await waitFor(() => {
      expect(screen.getByText('channelDeleteInstanceTitle')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'channelDeleteInstanceConfirm' }));
    await waitFor(() => {
      expect(mockDeleteChannelInstance).toHaveBeenCalledWith('inst1');
    });
  });
});
