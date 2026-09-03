import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { DataFlowDisclosurePanel } from '../DataFlowDisclosurePanel';
import useProviderStore from '@/store/useProviderStore';
import useConfigStore from '@/store/useConfigStore';

const {
  mockIsSandbox,
  mockIsTauriRuntime,
  mockApiRequest,
  mockListConnectorStatus,
  mockListOAuthCredentials,
  mockListChannelStatuses,
} = vi.hoisted(() => ({
  mockIsSandbox: vi.fn(() => false),
  mockIsTauriRuntime: vi.fn(() => false),
  mockApiRequest: vi.fn(),
  mockListConnectorStatus: vi.fn(),
  mockListOAuthCredentials: vi.fn(),
  mockListChannelStatuses: vi.fn(),
}));

const stableT = (key: string, values?: Record<string, unknown>) => {
  if (key === 'badgeActiveCount' && values && 'count' in values) {
    return `active:${values.count}`;
  }
  if (key.startsWith('dataUsage.')) {
    return key;
  }
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('next/link', () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock('@/lib/deploy-mode', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/deploy-mode')>();
  return {
    ...actual,
    isSandbox: mockIsSandbox,
    isTauriRuntime: mockIsTauriRuntime,
  };
});

vi.mock('@/lib/api', () => ({
  apiRequest: mockApiRequest,
}));

vi.mock('@/services/connect', () => ({
  listConnectorStatus: mockListConnectorStatus,
}));

vi.mock('@/services/integrations/oauthCredentials', () => ({
  listOAuthCredentials: mockListOAuthCredentials,
}));

vi.mock('@/services/channels/manage', () => ({
  listChannelStatuses: mockListChannelStatuses,
}));

vi.mock('@/services/memory/core', () => ({
  exportMemories: vi.fn(),
}));

vi.mock('../SettingsSection', () => ({
  default: ({ title, description, children }: { title: string; description: string; children: React.ReactNode }) => (
    <div data-testid="settings-section">
      <h3>{title}</h3>
      <p>{description}</p>
      {children}
    </div>
  ),
}));

describe('DataFlowDisclosurePanel', () => {
  beforeEach(() => {
    mockIsSandbox.mockReturnValue(false);
    mockIsTauriRuntime.mockReturnValue(false);
    mockApiRequest.mockResolvedValue({ deploy_mode: 'local' });
    mockListConnectorStatus.mockResolvedValue([]);
    mockListOAuthCredentials.mockResolvedValue([]);
    mockListChannelStatuses.mockResolvedValue([]);
    useProviderStore.setState({ providers: [] });
    useConfigStore.setState({
      mcpConfigs: [],
      privacyEnabled: false,
      privacyRouting: undefined,
    });
  });

  it('renders local private domain components properly', async () => {
    render(<DataFlowDisclosurePanel />);

    expect(screen.getByText('localDomain')).toBeDefined();
    expect(screen.getByText('localChatHistory')).toBeDefined();

    await waitFor(() => {
      expect(screen.getByText('noEgress')).toBeDefined();
      expect(mockListConnectorStatus).toHaveBeenCalled();
      expect(mockListOAuthCredentials).toHaveBeenCalled();
      expect(mockListChannelStatuses).not.toHaveBeenCalled();
    });
  });

  it('renders active providers and mcp servers dynamically in egress section', async () => {
    useProviderStore.setState({
      providers: [
        {
          id: 'anthropic',
          name: 'Anthropic Claude',
          apiUrl: 'https://api.anthropic.com',
          apiKey: 'sk-ant-test',
          isEnabled: true,
          models: [],
        },
      ],
    });
    useConfigStore.setState({
      mcpConfigs: [
        {
          name: 'filesystem-server',
          enabled: true,
          type: 'stdio',
          command: 'npx -y @modelcontextprotocol/server-filesystem',
        },
      ],
    });

    render(<DataFlowDisclosurePanel />);

    await waitFor(() => {
      expect(screen.getByText('Anthropic Claude')).toBeDefined();
      expect(screen.getByText('filesystem-server')).toBeDefined();
      expect(screen.getByText('active:2')).toBeDefined();
    });
  });

  it('shows hosted control plane copy in sandbox deploy mode', async () => {
    mockIsSandbox.mockReturnValue(true);
    mockApiRequest.mockResolvedValue({ deploy_mode: 'sandbox' });

    render(<DataFlowDisclosurePanel />);

    await waitFor(() => {
      expect(screen.getByText('controlPlaneHosted')).toBeDefined();
      expect(screen.getByText('controlPlaneHostedDesc')).toBeDefined();
      expect(screen.queryByText('controlPlaneStandaloneDesc')).toBeNull();
    });
  });

  it('lists connected external connectors in egress section', async () => {
    mockListConnectorStatus.mockResolvedValue([
      {
        profile_id: 'slack',
        label: 'Slack',
        status: 'ready',
        agent_id: 'default',
        doctor_ok: true,
        last_doctor_detail: 'ok',
        connected_at: '2026-08-31T12:00:00Z',
        last_doctor_at: '2026-08-31T12:00:00Z',
      },
      {
        profile_id: 'notion',
        label: 'Notion',
        status: 'missing',
        agent_id: 'default',
        doctor_ok: false,
        last_doctor_detail: 'missing',
        connected_at: null,
        last_doctor_at: null,
      },
    ]);

    render(<DataFlowDisclosurePanel />);

    await waitFor(() => {
      expect(screen.getByText('Slack')).toBeDefined();
      expect(screen.queryByText('Notion')).toBeNull();
      expect(screen.getByText('active:1')).toBeDefined();
    });
  });

  it('shows cross-border routing hint when privacy routing is configured with cloud egress', async () => {
    useProviderStore.setState({
      providers: [
        {
          id: 'openai',
          name: 'OpenAI',
          apiUrl: 'https://api.openai.com/v1',
          apiKey: 'sk-test',
          isEnabled: true,
          models: [],
        },
      ],
    });
    useConfigStore.setState({
      mcpConfigs: [],
      privacyEnabled: true,
      privacyRouting: { localModel: 'llama3:8b' },
    });

    render(<DataFlowDisclosurePanel />);

    await waitFor(() => {
      expect(screen.getByText(/crossBorderRoutingHint/)).toBeDefined();
      expect(screen.getByText('crossBorderRoutingLink')).toBeDefined();
    });
  });

  it('lists connected oauth integrations in egress section', async () => {
    mockListOAuthCredentials.mockResolvedValue([
      {
        issuer: 'slack',
        user_id: 'U123',
        scope: 'chat:write',
        expires_at: null,
        connected: true,
      },
    ]);

    render(<DataFlowDisclosurePanel />);

    await waitFor(() => {
      expect(screen.getByText('Slack')).toBeDefined();
      expect(screen.getByText('active:1')).toBeDefined();
    });
  });

  it('shows sync egress immediately while integrations are still loading', async () => {
    mockListConnectorStatus.mockImplementation(() => new Promise((resolve) => setTimeout(() => resolve([]), 50)));
    mockListOAuthCredentials.mockResolvedValue([]);
    useProviderStore.setState({
      providers: [
        {
          id: 'openai',
          name: 'OpenAI',
          apiUrl: 'https://api.openai.com/v1',
          apiKey: 'sk-test',
          isEnabled: true,
          models: [],
        },
      ],
    });

    render(<DataFlowDisclosurePanel />);

    expect(screen.getByText('OpenAI')).toBeDefined();
    expect(screen.getByText('integrationsLoading')).toBeDefined();
  });

  it('lists connected messaging channels in egress when running in Tauri', async () => {
    mockIsTauriRuntime.mockReturnValue(true);
    mockListChannelStatuses.mockResolvedValue([
      {
        name: 'telegram-main',
        status: 'connected',
        connected: true,
        channelType: 'telegram',
        instanceId: 'tg-inst-1',
        displayName: 'Telegram Bot',
        last_inbound_at: null,
        last_outbound_at: null,
        last_active_at: null,
        issues: [],
      },
      {
        name: 'whatsapp-backup',
        status: 'disconnected',
        connected: false,
        channelType: 'whatsapp',
        instanceId: 'wa-inst-1',
        displayName: 'WhatsApp',
        last_inbound_at: null,
        last_outbound_at: null,
        last_active_at: null,
        issues: [],
      },
    ]);

    render(<DataFlowDisclosurePanel />);

    await waitFor(() => {
      expect(mockListChannelStatuses).toHaveBeenCalled();
      expect(screen.getByText('Telegram Bot')).toBeDefined();
      expect(screen.queryByText('WhatsApp')).toBeNull();
      expect(screen.getByText('active:1')).toBeDefined();
      expect(screen.getByText('channelCategory')).toBeDefined();
    });

    const manageLinks = screen.getAllByText('actionManage');
    const channelLink = manageLinks
      .map((node) => node.closest('a'))
      .find((anchor) => anchor?.getAttribute('href') === '/settings/channels');
    expect(channelLink).toBeDefined();
  });

  it('refetches integrations when channel-status-change event is dispatched', async () => {
    mockIsTauriRuntime.mockReturnValue(true);
    mockListChannelStatuses.mockResolvedValueOnce([]).mockResolvedValueOnce([
      {
        name: 'telegram-main',
        status: 'connected',
        connected: true,
        channelType: 'telegram',
        instanceId: 'tg-inst-1',
        displayName: 'Telegram Bot',
        last_inbound_at: null,
        last_outbound_at: null,
        last_active_at: null,
        issues: [],
      },
    ]);

    render(<DataFlowDisclosurePanel />);

    await waitFor(() => {
      expect(mockListChannelStatuses).toHaveBeenCalled();
    });

    const callsBeforeEvent = mockListChannelStatuses.mock.calls.length;

    window.dispatchEvent(
      new CustomEvent('channel-status-change', {
        detail: { channel: 'telegram', status: 'connected', type: 'channel_connected' },
      }),
    );

    await waitFor(() => {
      expect(mockListChannelStatuses.mock.calls.length).toBe(callsBeforeEvent + 1);
      expect(screen.getByText('Telegram Bot')).toBeDefined();
    });
  });

  it('refetches integrations when channel-credentials-saved event is dispatched', async () => {
    mockIsTauriRuntime.mockReturnValue(true);
    mockListChannelStatuses.mockResolvedValueOnce([]).mockResolvedValueOnce([
      {
        name: 'feishu-main',
        status: 'connected',
        connected: true,
        channelType: 'feishu',
        instanceId: 'fs-inst-1',
        displayName: 'Feishu Bot',
        last_inbound_at: null,
        last_outbound_at: null,
        last_active_at: null,
        issues: [],
      },
    ]);

    render(<DataFlowDisclosurePanel />);

    await waitFor(() => {
      expect(mockListChannelStatuses).toHaveBeenCalled();
    });

    const callsBeforeEvent = mockListChannelStatuses.mock.calls.length;

    window.dispatchEvent(new CustomEvent('channel-credentials-saved'));

    await waitFor(() => {
      expect(mockListChannelStatuses.mock.calls.length).toBe(callsBeforeEvent + 1);
      expect(screen.getByText('Feishu Bot')).toBeDefined();
    });
  });

  it('does not show cross-border hint when only messaging channels are active', async () => {
    mockIsTauriRuntime.mockReturnValue(true);
    mockListChannelStatuses.mockResolvedValue([
      {
        name: 'telegram-main',
        status: 'connected',
        connected: true,
        channelType: 'telegram',
        instanceId: 'tg-inst-1',
        displayName: 'Telegram Bot',
        last_inbound_at: null,
        last_outbound_at: null,
        last_active_at: null,
        issues: [],
      },
    ]);
    useConfigStore.setState({
      mcpConfigs: [],
      privacyEnabled: true,
      privacyRouting: { localModel: 'llama3:8b' },
    });

    render(<DataFlowDisclosurePanel />);

    await waitFor(() => {
      expect(screen.getByText('Telegram Bot')).toBeDefined();
      expect(screen.queryByText(/crossBorderRoutingHint/)).toBeNull();
    });
  });

  it('does not show cross-border hint for local-only LLM providers', async () => {
    useProviderStore.setState({
      providers: [
        {
          id: 'ollama',
          name: 'Ollama',
          apiUrl: 'http://127.0.0.1:11434',
          apiKey: '',
          isEnabled: true,
          models: [],
        },
      ],
    });
    useConfigStore.setState({
      mcpConfigs: [],
      privacyEnabled: true,
      privacyRouting: { localModel: 'llama3:8b' },
    });

    render(<DataFlowDisclosurePanel />);

    await waitFor(() => {
      expect(screen.getByText('Ollama')).toBeDefined();
      expect(screen.queryByText(/crossBorderRoutingHint/)).toBeNull();
    });
  });

  it('degrades gracefully when integration APIs reject', async () => {
    mockListConnectorStatus.mockRejectedValue(new Error('connect offline'));
    mockListOAuthCredentials.mockRejectedValue(new Error('oauth offline'));
    mockIsTauriRuntime.mockReturnValue(true);
    mockListChannelStatuses.mockRejectedValue(new Error('channels offline'));

    render(<DataFlowDisclosurePanel />);

    await waitFor(() => {
      expect(screen.getByText('noEgress')).toBeDefined();
      expect(mockListConnectorStatus).toHaveBeenCalled();
      expect(mockListOAuthCredentials).toHaveBeenCalled();
      expect(mockListChannelStatuses).toHaveBeenCalled();
    });
  });

  it('renders your rights export section', async () => {
    render(<DataFlowDisclosurePanel />);

    await waitFor(() => {
      expect(screen.getByText('yourRightsTitle')).toBeDefined();
      expect(screen.getByText('rightsExportButton')).toBeDefined();
      expect(screen.getByText('rightsManageMemory')).toBeDefined();
    });
  });
});
