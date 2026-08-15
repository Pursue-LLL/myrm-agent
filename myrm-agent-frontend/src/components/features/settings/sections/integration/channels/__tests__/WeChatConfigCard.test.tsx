/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const mocks = vi.hoisted(() => ({
  getWeChatStatus: vi.fn(),
  logoutWeChatChannel: vi.fn(),
  listChannelInstances: vi.fn(),
  deleteChannelInstance: vi.fn(),
  createChannelInstance: vi.fn(),
  updateChannelDisplayName: vi.fn(),
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
}));

const {
  getWeChatStatus: mockGetWeChatStatus,
  logoutWeChatChannel: mockLogoutWeChatChannel,
  listChannelInstances: mockListChannelInstances,
  deleteChannelInstance: mockDeleteChannelInstance,
  createChannelInstance: mockCreateChannelInstance,
  updateChannelDisplayName: mockUpdateChannelDisplayName,
  toastSuccess: mockToastSuccess,
  toastError: mockToastError,
} = mocks;

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
    success: (...args: unknown[]) => mockToastSuccess(...args),
    error: (...args: unknown[]) => mockToastError(...args),
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

  it('keeps the confirm dialog open and toasts when primary logout fails', async () => {
    mockLogoutWeChatChannel.mockRejectedValue(new Error('logout failed'));
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
      expect(mockToastError).toHaveBeenCalledWith('wechatInstanceRemoveError');
    });
    // 失败时对话框必须保持打开（ConfirmDialog 捕获错误后不关闭）
    expect(screen.getByText('channelDeleteInstanceTitle')).toBeInTheDocument();
    // 账户卡片仍在（未登出）
    expect(screen.getByLabelText('delete-wechat')).toBeInTheDocument();
  });

  it('keeps the confirm dialog open and toasts when extra instance delete fails', async () => {
    mockListChannelInstances.mockResolvedValue([
      {
        instanceId: 'inst1',
        channelType: 'wechat',
        channelName: 'wechat_inst1',
        displayName: '客服微信',
      },
    ]);
    mockDeleteChannelInstance.mockRejectedValue(new Error('delete failed'));

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
      expect(mockToastError).toHaveBeenCalledWith('wechatInstanceRemoveError');
    });
    // 失败时对话框保持打开，实例卡片仍在
    expect(screen.getByText('channelDeleteInstanceTitle')).toBeInTheDocument();
    expect(screen.getByLabelText('delete-wechat_inst1')).toBeInTheDocument();
  });
});
