import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {
  buildChannelEgressSnapshot,
  buildComplianceExportBundle,
  buildConnectorEgressSnapshot,
  buildOAuthEgressSnapshot,
  DataFlowYourRightsStrip,
  redactPrivacyRoutingSnapshot,
} from '../DataFlowYourRightsStrip';
import useConfigStore from '@/store/useConfigStore';

const { mockExportMemories, mockToastSuccess, mockToastError } = vi.hoisted(() => ({
  mockExportMemories: vi.fn(),
  mockToastSuccess: vi.fn(),
  mockToastError: vi.fn(),
}));

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('next/link', () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock('@/services/memory/core', () => ({
  exportMemories: mockExportMemories,
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: {
    success: mockToastSuccess,
    error: mockToastError,
  },
}));

describe('DataFlowYourRightsStrip export helpers', () => {
  it('redacts localApiKey in privacy routing snapshot', () => {
    const redacted = redactPrivacyRoutingSnapshot({
      localModel: 'llama3:8b',
      localApiKey: 'sk-secret-key',
    });

    expect(redacted).toEqual({
      localModel: 'llama3:8b',
      localApiKey: '[REDACTED]',
    });
  });

  it('preserves routing snapshot when localApiKey is absent', () => {
    const routing = { localModel: 'llama3:8b' };
    expect(redactPrivacyRoutingSnapshot(routing)).toEqual(routing);
    expect(redactPrivacyRoutingSnapshot(null)).toBeNull();
  });

  it('buildComplianceExportBundle never includes raw localApiKey', () => {
    const bundle = buildComplianceExportBundle(
      { version: 1, total_count: 0, data: [] },
      {
        enabled: true,
        s2_action: 'mask',
        s3_action: 'block',
        deep_scan: false,
        routing: { localModel: 'llama3:8b', localApiKey: 'sk-leak-me' },
      },
      {
        providers: [],
        mcp: [],
        connectors: [],
        oauthIntegrations: [],
        channels: [],
      },
      '2026-08-31T12:00:00.000Z',
    );

    expect(bundle.privacy_settings.routing?.localApiKey).toBe('[REDACTED]');
    expect(JSON.stringify(bundle)).not.toContain('sk-leak-me');
  });

  it('buildChannelEgressSnapshot includes only connected channels', () => {
    expect(
      buildChannelEgressSnapshot([
        {
          name: 'telegram-1',
          status: 'connected',
          connected: true,
          channelType: 'telegram',
          instanceId: 'inst-1',
          displayName: 'My Telegram',
          last_inbound_at: null,
          last_outbound_at: null,
          last_active_at: null,
          issues: [],
        },
        {
          name: 'whatsapp-1',
          status: 'disconnected',
          connected: false,
          channelType: 'whatsapp',
          instanceId: 'inst-2',
          displayName: 'WhatsApp',
          last_inbound_at: null,
          last_outbound_at: null,
          last_active_at: null,
          issues: [],
        },
      ]),
    ).toEqual([
      {
        instanceId: 'inst-1',
        channelType: 'telegram',
        displayName: 'My Telegram',
      },
    ]);
  });

  it('buildConnectorEgressSnapshot includes only ready connected connectors', () => {
    expect(
      buildConnectorEgressSnapshot([
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
      ]),
    ).toEqual([{ profileId: 'slack', label: 'Slack' }]);
  });

  it('buildOAuthEgressSnapshot includes only connected integrations', () => {
    expect(
      buildOAuthEgressSnapshot([
        {
          issuer: 'slack',
          user_id: 'U123',
          scope: 'chat:write',
          expires_at: null,
          connected: true,
        },
        {
          issuer: 'github',
          user_id: null,
          scope: null,
          expires_at: null,
          connected: false,
        },
      ]),
    ).toEqual([{ issuer: 'slack' }]);
  });

  it('buildComplianceExportBundle preserves channel egress snapshot', () => {
    const bundle = buildComplianceExportBundle(
      { version: 1, total_count: 0, data: [] },
      {
        enabled: false,
        s2_action: undefined,
        s3_action: undefined,
        deep_scan: undefined,
        routing: null,
      },
      {
        providers: [],
        mcp: [],
        connectors: [],
        oauthIntegrations: [],
        channels: [{ instanceId: 'inst-1', channelType: 'telegram', displayName: 'TG' }],
      },
    );

    expect(bundle.egress_snapshot.channels).toEqual([
      { instanceId: 'inst-1', channelType: 'telegram', displayName: 'TG' },
    ]);
  });
});

describe('DataFlowYourRightsStrip component', () => {
  const egressSnapshot = {
    providers: [],
    mcp: [],
    connectors: [],
    oauthIntegrations: [],
    channels: [],
  };

  beforeEach(() => {
    mockExportMemories.mockReset();
    mockToastSuccess.mockReset();
    mockToastError.mockReset();
    useConfigStore.setState({
      privacyEnabled: true,
      privacyS2Action: 'mask',
      privacyS3Action: 'block',
      privacyDeepScan: false,
      privacyRouting: { localModel: 'llama3:8b', localApiKey: 'sk-secret' },
    });
  });

  it('downloads compliance export and shows success toast', async () => {
    mockExportMemories.mockResolvedValue({ version: 1, total_count: 0, data: [] });
    const createObjectURL = vi.fn(() => 'blob:export');
    const revokeObjectURL = vi.fn();
    vi.stubGlobal('URL', {
      createObjectURL,
      revokeObjectURL,
    });

    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

    render(<DataFlowYourRightsStrip egressSnapshot={egressSnapshot} />);

    await userEvent.click(screen.getByRole('button', { name: 'rightsExportButton' }));

    await waitFor(() => {
      expect(mockExportMemories).toHaveBeenCalled();
      expect(mockToastSuccess).toHaveBeenCalledWith('rightsExportSuccess');
      expect(createObjectURL).toHaveBeenCalled();
    });

    const blob = createObjectURL.mock.calls[0]?.[0] as Blob;
    expect(blob).toBeInstanceOf(Blob);
    const downloaded = JSON.parse(await blob.text());
    expect(downloaded.privacy_settings.routing.localApiKey).toBe('[REDACTED]');

    clickSpy.mockRestore();
    vi.unstubAllGlobals();
  });

  it('shows error toast when export fails', async () => {
    mockExportMemories.mockRejectedValue(new Error('export failed'));

    render(<DataFlowYourRightsStrip egressSnapshot={egressSnapshot} />);

    await userEvent.click(screen.getByRole('button', { name: 'rightsExportButton' }));

    await waitFor(() => {
      expect(mockToastError).toHaveBeenCalledWith('rightsExportFailed');
    });
  });
});
