/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import type { CatalogEntry } from './catalog-types';

const mockApiRequest = vi.fn();
const mockSetMCPConfigs = vi.fn();
const mockGateMcpEnable = vi.fn();
const mockIsSandbox = vi.fn();
const mockToast = vi.fn();

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/hooks/shared/useToast', () => ({
  toast: (...args: unknown[]) => mockToast(...args),
}));

vi.mock('@/store/useConfigStore', () => ({
  default: () => ({
    mcpConfigs: [],
    setMCPConfigs: mockSetMCPConfigs,
  }),
}));

vi.mock('@/lib/api', () => ({
  BACKEND_BASE_URL: 'http://127.0.0.1:8080',
  apiRequest: (...args: unknown[]) => mockApiRequest(...args),
}));

vi.mock('@/hooks/settings/useMcpSecurityGate', () => ({
  buildLastScanSummary: () => null,
  gateMcpEnable: (...args: unknown[]) => mockGateMcpEnable(...args),
}));

vi.mock('@/lib/utils/mcpScanFindingText', () => ({
  formatMcpGateBlockedMessage: () => 'blocked',
}));

vi.mock('@/components/features/settings/mcp/MCPScanAckDialog', () => ({
  MCPScanAckDialog: () => null,
}));

vi.mock('@/lib/deploy-mode', () => ({
  isSandbox: () => mockIsSandbox(),
  getDocsUrl: (path: string = '/') => `https://docs.myrm.ai${path === '/' ? '' : path}`,
}));

import { IntegrationConnectDialog } from './IntegrationConnectDialog';

function makeCatalogEntry(overrides?: Partial<CatalogEntry>): CatalogEntry {
  return {
    id: 'unreal-engine',
    name: 'Unreal Engine',
    nameZh: 'Unreal Engine',
    description: 'Drive Unreal via MCP',
    descriptionZh: '通过 MCP 驱动 Unreal',
    icon: 'unreal',
    category: 'design',
    connectorType: 'mcp',
    authType: 'none',
    helpUrl: null,
    helpText: null,
    helpTextZh: null,
    envKey: null,
    credentialFields: null,
    tags: [],
    website: null,
    mcpConfig: {
      name: 'unreal-engine',
      type: 'streamable_http',
      url: 'http://127.0.0.1:8000/mcp',
    },
    deploymentScope: 'local_tauri_only',
    postConnectGuide: null,
    postConnectGuideZh: null,
    ...overrides,
  };
}

describe('IntegrationConnectDialog', () => {
  beforeEach(() => {
    mockApiRequest.mockReset();
    mockSetMCPConfigs.mockReset();
    mockGateMcpEnable.mockReset();
    mockToast.mockReset();
    mockIsSandbox.mockReset();
    mockIsSandbox.mockReturnValue(true);
    mockGateMcpEnable.mockResolvedValue({
      needsAcknowledgement: false,
      allowed: true,
      scanResult: { findings: [] },
      verifyError: null,
      verifyFindings: [],
    });
  });

  it('blocks local-only entries in sandbox without probe url', async () => {
    const entry = makeCatalogEntry();
    const onClose = vi.fn();
    const openSpy = vi.spyOn(window, 'open').mockReturnValue({} as Window);
    render(
      <IntegrationConnectDialog
        entry={entry}
        locale="en"
        onClose={onClose}
        onConnected={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'connect' }));

    await waitFor(() => {
      expect(screen.getByText('probeCloudLoopbackBlocked')).toBeInTheDocument();
    });
    expect(mockApiRequest).not.toHaveBeenCalled();
    expect(mockSetMCPConfigs).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'probeRecommendedActionSwitchMode' }));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(openSpy).toHaveBeenCalledWith(
      'https://docs.myrm.ai/getting-started/local-deployment',
      '_blank',
      'noopener,noreferrer',
    );
    openSpy.mockRestore();
  });

  it('blocks connect when probe response carries shouldBlockConnect=true', async () => {
    const entry = makeCatalogEntry({
      deploymentScope: 'all_modes',
      mcpConfig: {
        name: 'unreal-engine',
        type: 'streamable_http',
        url: 'http://127.0.0.1:8000/mcp',
        probeUrl: 'http://127.0.0.1:8000/mcp',
      },
    });
    mockIsSandbox.mockReturnValue(false);
    mockApiRequest.mockResolvedValueOnce({
      status: 'cloud_not_supported',
      shouldBlockConnect: true,
    });

    render(
      <IntegrationConnectDialog
        entry={entry}
        locale="en"
        onClose={vi.fn()}
        onConnected={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'connect' }));

    await waitFor(() => {
      expect(screen.getByText('probeCloudLoopbackBlocked')).toBeInTheDocument();
    });
    expect(mockApiRequest).toHaveBeenCalledTimes(1);
    expect(mockSetMCPConfigs).not.toHaveBeenCalled();
  });

  it('falls back to mcp url when probeUrl is missing', async () => {
    const entry = makeCatalogEntry({
      deploymentScope: 'all_modes',
      mcpConfig: {
        name: 'unreal-engine',
        type: 'streamable_http',
        url: 'http://127.0.0.1:7001/mcp',
      },
    });
    mockIsSandbox.mockReturnValue(false);
    mockApiRequest.mockResolvedValueOnce({
      status: 'unreachable',
      reasonCode: 'connection_refused',
      shouldBlockConnect: true,
      recommendedMode: 'start_local_editor_mcp',
      error: 'raw backend detail should not be exposed in toc',
    });

    render(
      <IntegrationConnectDialog
        entry={entry}
        locale="en"
        onClose={vi.fn()}
        onConnected={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'connect' }));

    await waitFor(() => {
      expect(screen.getByText('probeConnectionRefused')).toBeInTheDocument();
    });
    expect(mockApiRequest).toHaveBeenCalledTimes(1);
    const firstCallOptions = mockApiRequest.mock.calls[0]?.[1] as { body?: string } | undefined;
    const requestBody = JSON.parse(firstCallOptions?.body ?? '{}') as { url?: string };
    expect(requestBody.url).toBe('http://127.0.0.1:7001/mcp');
  });

  it('renders recommendedMode guidance and retries probe for start_local_editor_mcp', async () => {
    const entry = makeCatalogEntry({
      deploymentScope: 'all_modes',
      mcpConfig: {
        name: 'unreal-engine',
        type: 'streamable_http',
        url: 'http://127.0.0.1:8000/mcp',
        probeUrl: 'http://127.0.0.1:8000/mcp',
      },
    });
    mockIsSandbox.mockReturnValue(false);
    mockApiRequest
      .mockResolvedValueOnce({
        status: 'unreachable',
        reasonCode: 'connection_refused',
        recommendedMode: 'start_local_editor_mcp',
        error: 'Connection refused',
      })
      .mockResolvedValueOnce({
        status: 'reachable',
      });

    render(
      <IntegrationConnectDialog
        entry={entry}
        locale="en"
        onClose={vi.fn()}
        onConnected={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'connect' }));

    await waitFor(() => {
      expect(screen.getByText('probeRecommendedModeStartLocalEditorMcp')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'probeRecommendedActionRetryProbe' }));

    await waitFor(() => {
      expect(mockApiRequest).toHaveBeenCalledTimes(2);
    });
    await waitFor(() => {
      expect(mockSetMCPConfigs).toHaveBeenCalledTimes(1);
    });
  });

  it('retries probe and auto-connects for verify_local_network_and_editor', async () => {
    const entry = makeCatalogEntry({
      deploymentScope: 'all_modes',
      mcpConfig: {
        name: 'unreal-engine',
        type: 'streamable_http',
        url: 'http://127.0.0.1:8000/mcp',
        probeUrl: 'http://127.0.0.1:8000/mcp',
      },
    });
    mockIsSandbox.mockReturnValue(false);
    mockApiRequest
      .mockResolvedValueOnce({
        status: 'unreachable',
        reasonCode: 'connection_timeout',
        recommendedMode: 'verify_local_network_and_editor',
        error: 'Connection timed out — host unreachable',
      })
      .mockResolvedValueOnce({
        status: 'reachable',
      });

    render(
      <IntegrationConnectDialog
        entry={entry}
        locale="en"
        onClose={vi.fn()}
        onConnected={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'connect' }));

    await waitFor(() => {
      expect(screen.getByText('probeRecommendedModeVerifyLocalNetworkAndEditor')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'probeRecommendedActionRetryProbe' }));

    await waitFor(() => {
      expect(mockApiRequest).toHaveBeenCalledTimes(2);
    });
    await waitFor(() => {
      expect(mockSetMCPConfigs).toHaveBeenCalledTimes(1);
    });
  });

  it('uses switch-mode action when backend recommends local_or_tauri', async () => {
    const entry = makeCatalogEntry({
      deploymentScope: 'all_modes',
      mcpConfig: {
        name: 'unreal-engine',
        type: 'streamable_http',
        url: 'http://127.0.0.1:8000/mcp',
        probeUrl: 'http://127.0.0.1:8000/mcp',
      },
    });
    const onClose = vi.fn();
    const openSpy = vi.spyOn(window, 'open').mockReturnValue({} as Window);
    mockIsSandbox.mockReturnValue(false);
    mockApiRequest.mockResolvedValueOnce({
      status: 'cloud_not_supported',
      shouldBlockConnect: true,
      recommendedMode: 'local_or_tauri',
    });

    render(
      <IntegrationConnectDialog
        entry={entry}
        locale="en"
        onClose={onClose}
        onConnected={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'connect' }));

    await waitFor(() => {
      expect(screen.getByText('probeRecommendedModeLocalOrTauri')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'probeRecommendedActionSwitchMode' }));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(openSpy).toHaveBeenCalledWith(
      'https://docs.myrm.ai/getting-started/local-deployment',
      '_blank',
      'noopener,noreferrer',
    );
    expect(mockApiRequest).toHaveBeenCalledTimes(1);
    expect(mockSetMCPConfigs).not.toHaveBeenCalled();
    openSpy.mockRestore();
  });

  it('shows localized TLS probe message for tls_verification_failed reasonCode', async () => {
    const entry = makeCatalogEntry({
      deploymentScope: 'all_modes',
      mcpConfig: {
        name: 'unreal-engine',
        type: 'streamable_http',
        url: 'http://127.0.0.1:8000/mcp',
        probeUrl: 'http://127.0.0.1:8000/mcp',
      },
    });
    mockIsSandbox.mockReturnValue(false);
    mockApiRequest.mockResolvedValueOnce({
      status: 'unreachable',
      reasonCode: 'tls_verification_failed',
      error: 'TLS certificate verification failed — trust the MCP certificate or configure a valid CA bundle',
    });

    render(
      <IntegrationConnectDialog
        entry={entry}
        locale="en"
        onClose={vi.fn()}
        onConnected={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'connect' }));

    await waitFor(() => {
      expect(screen.getByText('probeTlsVerificationFailed')).toBeInTheDocument();
    });
    expect(mockApiRequest).toHaveBeenCalledTimes(1);
    expect(mockSetMCPConfigs).not.toHaveBeenCalled();
  });

  it.each([
    ['connection_refused', 'probeConnectionRefused', 'start_local_editor_mcp'],
    ['connection_unreachable', 'probeConnectionUnreachable', 'verify_local_network_and_editor'],
    ['connection_timeout', 'probeConnectionTimeout', 'verify_local_network_and_editor'],
    ['probe_failed_unknown', 'probeUnknownFailure', 'verify_local_network_and_editor'],
    ['unexpected_reason_code', 'probeUnknownFailure', 'start_local_editor_mcp'],
  ])('shows localized probe message for %s', async (reasonCode, expectedMessageKey, recommendedMode) => {
    const onClose = vi.fn();
    mockIsSandbox.mockReturnValue(false);
    mockApiRequest.mockResolvedValueOnce({
      status: 'unreachable',
      reasonCode,
      shouldBlockConnect: true,
      recommendedMode,
      error: 'raw backend detail should not be exposed in toc',
    });

    render(
      <IntegrationConnectDialog
        entry={makeCatalogEntry({
          mcpConfig: {
            url: 'http://127.0.0.1:7777/mcp',
            probeUrl: 'http://127.0.0.1:7777/mcp',
          },
        })}
        locale="zh"
        onClose={onClose}
        onConnected={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'connect' }));

    await waitFor(() => {
      expect(screen.getByText(expectedMessageKey)).toBeInTheDocument();
    });
    expect(mockApiRequest).toHaveBeenCalledTimes(1);
    expect(mockSetMCPConfigs).not.toHaveBeenCalled();
  });

  it('renders helpText and learnMore link for auth=none entries', () => {
    const entry = makeCatalogEntry({
      authType: 'none',
      helpText: 'Sign in with your Microsoft account through the assistant.',
      helpTextZh: '通过助手使用你的 Microsoft 账户登录。',
      helpUrl: 'https://to-do.office.com',
    });

    render(
      <IntegrationConnectDialog
        entry={entry}
        locale="en"
        onClose={vi.fn()}
        onConnected={vi.fn()}
      />,
    );

    expect(screen.getByText('Sign in with your Microsoft account through the assistant.')).toBeInTheDocument();
    expect(screen.queryByText('noAuthRequired')).not.toBeInTheDocument();
    const link = screen.getByRole('link', { name: 'learnMore' });
    expect(link).toHaveAttribute('href', 'https://to-do.office.com');
    expect(link).toHaveAttribute('target', '_blank');
  });

  it('renders localized helpTextZh for auth=none entries in zh locale', () => {
    const entry = makeCatalogEntry({
      authType: 'none',
      helpText: 'English help',
      helpTextZh: '通过助手使用你的 Microsoft 账户登录。',
    });

    render(
      <IntegrationConnectDialog
        entry={entry}
        locale="zh"
        onClose={vi.fn()}
        onConnected={vi.fn()}
      />,
    );

    expect(screen.getByText('通过助手使用你的 Microsoft 账户登录。')).toBeInTheDocument();
    expect(screen.queryByText('English help')).not.toBeInTheDocument();
  });

  it('falls back to noAuthRequired when helpText is absent for auth=none entries', () => {
    const entry = makeCatalogEntry({
      authType: 'none',
      helpText: null,
      helpUrl: null,
    });

    render(
      <IntegrationConnectDialog
        entry={entry}
        locale="en"
        onClose={vi.fn()}
        onConnected={vi.fn()}
      />,
    );

    expect(screen.getByText('noAuthRequired')).toBeInTheDocument();
  });

  it('omits learnMore link when helpUrl is absent for auth=none entries', () => {
    const entry = makeCatalogEntry({
      authType: 'none',
      helpText: 'No API key needed',
    });

    render(
      <IntegrationConnectDialog
        entry={entry}
        locale="en"
        onClose={vi.fn()}
        onConnected={vi.fn()}
      />,
    );

    expect(screen.getByText('No API key needed')).toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });
});
