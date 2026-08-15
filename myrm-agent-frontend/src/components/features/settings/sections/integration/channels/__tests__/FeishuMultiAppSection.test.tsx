/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const mockListChannelStatuses = vi.fn();
const mockListChannelInstances = vi.fn();
const mockGetChannelInstanceMeta = vi.fn();
const mockCreateChannelInstance = vi.fn();
const mockDeleteChannelInstance = vi.fn();
const mockUpdateChannelDisplayName = vi.fn();
const mockGetChannelCredentials = vi.fn();

vi.mock('@/services/channels', async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return {
    ...actual,
    listChannelStatuses: (...args: unknown[]) => mockListChannelStatuses(...args),
    listChannelInstances: (...args: unknown[]) => mockListChannelInstances(...args),
    getChannelInstanceMeta: (...args: unknown[]) => mockGetChannelInstanceMeta(...args),
    createChannelInstance: (...args: unknown[]) => mockCreateChannelInstance(...args),
    deleteChannelInstance: (...args: unknown[]) => mockDeleteChannelInstance(...args),
    updateChannelDisplayName: (...args: unknown[]) => mockUpdateChannelDisplayName(...args),
    getChannelCredentials: (...args: unknown[]) => mockGetChannelCredentials(...args),
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
    mockGetChannelInstanceMeta.mockResolvedValue({ maxInstancesPerType: 5 });
    mockListChannelStatuses.mockResolvedValue([]);
    mockDeleteChannelInstance.mockResolvedValue(undefined);
    mockUpdateChannelDisplayName.mockResolvedValue({ displayName: 'renamed' });
    mockGetChannelCredentials.mockResolvedValue({
      appId: 'cli_existing',
      appSecret: '••••rest',
      useLark: 'false',
    });
  });

  it('renders the multi-app section with empty state', async () => {
    render(<FeishuMultiAppSection />);

    await waitFor(() => {
      expect(screen.getByText('feishuMultiAppTitle')).toBeInTheDocument();
      expect(screen.getByText('feishuAddApp')).toBeInTheDocument();
      expect(screen.getByText('feishuScanToAdd')).toBeInTheDocument();
    });
    expect(mockListChannelInstances).toHaveBeenCalledWith('feishu');
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

  it('opens the credentials edit dialog from an instance card', async () => {
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

    fireEvent.click(screen.getByLabelText('edit-credentials-feishu_inst1'));

    await waitFor(() => {
      expect(screen.getByText('feishuCredentialsDialogTitle')).toBeInTheDocument();
      expect(mockGetChannelCredentials).toHaveBeenCalledWith('feishu_inst1');
    });
    expect(screen.getByDisplayValue('cli_existing')).toBeInTheDocument();
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
      expect(screen.getByText('channelDeleteInstanceTitle')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'channelDeleteInstanceConfirm' }));

    await waitFor(() => {
      expect(mockDeleteChannelInstance).toHaveBeenCalledWith('inst1');
    });
  });

  it('keeps the instance when the delete confirmation is cancelled', async () => {
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
      expect(screen.getByText('channelDeleteInstanceTitle')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'channelDeleteInstanceCancel' }));

    await waitFor(() => {
      expect(screen.queryByText('channelDeleteInstanceTitle')).not.toBeInTheDocument();
    });
    expect(mockDeleteChannelInstance).not.toHaveBeenCalled();
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

  it('disables the add-app button when total instances (default + extra) reach the limit', async () => {
    // Backend counts ALL instances of a type (including the default) against
    // _MAX_INSTANCES_PER_TYPE, so a default + 4 extra = 5 is already at the limit.
    const makeInst = (name: string, displayName: string, extra = false) => ({
      instanceId: extra ? `inst-${name}` : 'inst-default',
      channelType: 'feishu',
      channelName: name,
      displayName,
    });
    mockListChannelInstances.mockResolvedValue([
      makeInst('feishu', 'Default App'),
      ...Array.from({ length: 4 }, (_, i) => makeInst(`feishu_inst${i + 1}`, `App ${i + 1}`, true)),
    ]);

    render(<FeishuMultiAppSection />);

    await waitFor(() => {
      expect(screen.getByText('feishuMultiAppLimitReached')).toBeInTheDocument();
    });

    const addButton = screen.getByRole('button', { name: 'feishuAddApp' });
    expect(addButton).toBeDisabled();
    expect(screen.getByText('App 4')).toBeInTheDocument();
    // The default instance occupies one slot but is not rendered as a card.
    expect(screen.queryByText('Default App')).not.toBeInTheDocument();
  });

  it('keeps the add-app button enabled below the limit', async () => {
    const makeInst = (n: number) => ({
      instanceId: `inst${n}`,
      channelType: 'feishu',
      channelName: `feishu_inst${n}`,
      displayName: `App ${n}`,
    });
    // Default + 2 extra = 3 instances, below the 5 limit.
    mockListChannelInstances.mockResolvedValue([
      { instanceId: 'inst-default', channelType: 'feishu', channelName: 'feishu', displayName: 'Default App' },
      ...Array.from({ length: 2 }, (_, i) => makeInst(i + 1)),
    ]);

    render(<FeishuMultiAppSection />);

    await waitFor(() => {
      expect(screen.queryByText('feishuMultiAppLimitReached')).not.toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: 'feishuAddApp' })).toBeEnabled();
  });
});
