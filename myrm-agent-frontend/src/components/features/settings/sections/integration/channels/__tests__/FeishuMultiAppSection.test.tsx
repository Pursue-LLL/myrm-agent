/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const mockListChannelStatuses = vi.fn();
const mockListChannelInstances = vi.fn();
const mockCreateChannelInstance = vi.fn();
const mockDeleteChannelInstance = vi.fn();
const mockUpdateChannelDisplayName = vi.fn();

vi.mock('@/services/channels', async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return {
    ...actual,
    listChannelStatuses: (...args: unknown[]) => mockListChannelStatuses(...args),
    listChannelInstances: (...args: unknown[]) => mockListChannelInstances(...args),
    createChannelInstance: (...args: unknown[]) => mockCreateChannelInstance(...args),
    deleteChannelInstance: (...args: unknown[]) => mockDeleteChannelInstance(...args),
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

import { FeishuMultiAppSection } from '../FeishuMultiAppSection';

describe('FeishuMultiAppSection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListChannelInstances.mockResolvedValue([]);
    mockListChannelStatuses.mockResolvedValue([]);
    mockDeleteChannelInstance.mockResolvedValue(undefined);
    mockUpdateChannelDisplayName.mockResolvedValue({ displayName: 'renamed' });
  });

  it('renders the multi-app section with empty state', async () => {
    render(<FeishuMultiAppSection />);

    await waitFor(() => {
      expect(mockListChannelInstances).toHaveBeenCalledWith('feishu');
    });
    expect(screen.getByText('feishuMultiAppTitle')).toBeInTheDocument();
    expect(screen.getByText('feishuAddApp')).toBeInTheDocument();
    expect(screen.getByText('feishuScanToAdd')).toBeInTheDocument();
  });

  it('lists extra feishu instances with status and delete button', async () => {
    mockListChannelInstances.mockResolvedValue([
      {
        instanceId: 'inst1',
        channelType: 'feishu',
        channelName: 'feishu_inst1',
        displayName: '客服机器人',
      },
    ]);
    mockListChannelStatuses.mockResolvedValue([
      {
        name: 'feishu_inst1',
        status: 'running',
        connected: true,
        channelType: 'feishu',
        instanceId: 'inst1',
        displayName: '客服机器人',
        last_inbound_at: null,
        last_outbound_at: null,
        last_active_at: null,
      },
    ]);

    render(<FeishuMultiAppSection />);

    await waitFor(() => {
      expect(screen.getByText('客服机器人')).toBeInTheDocument();
    });
    expect(screen.getByText('feishu_inst1')).toBeInTheDocument();
    expect(screen.getByText('feishuConnected')).toBeInTheDocument();
  });

  it('deletes an instance after confirming', async () => {
    mockListChannelInstances.mockResolvedValue([
      {
        instanceId: 'inst1',
        channelType: 'feishu',
        channelName: 'feishu_inst1',
        displayName: '客服机器人',
      },
    ]);

    render(<FeishuMultiAppSection />);
    await waitFor(() => {
      expect(screen.getByText('客服机器人')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText('delete-feishu_inst1'));

    await waitFor(() => {
      expect(mockDeleteChannelInstance).toHaveBeenCalledWith('inst1');
    });
  });

  it('renames an instance display name', async () => {
    mockListChannelInstances.mockResolvedValue([
      {
        instanceId: 'inst1',
        channelType: 'feishu',
        channelName: 'feishu_inst1',
        displayName: '旧名称',
      },
    ]);

    render(<FeishuMultiAppSection />);
    await waitFor(() => {
      expect(screen.getByText('旧名称')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText('rename-feishu_inst1'));
    const input = screen.getByDisplayValue('旧名称');
    fireEvent.change(input, { target: { value: '新名称' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => {
      expect(mockUpdateChannelDisplayName).toHaveBeenCalledWith('feishu_inst1', '新名称');
    });
  });
});
