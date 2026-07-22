/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import type { CatalogEntry } from './catalog-types';

const mockApiRequest = vi.fn();
const mockSetMCPConfigs = vi.fn();
const mockGateMcpEnable = vi.fn();
const mockIsSandbox = vi.fn();
const mockToast = vi.fn();

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, opts?: { default?: string }) => opts?.default ?? key,
}));

vi.mock('@/hooks/useToast', () => ({
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

vi.mock('@/hooks/useMcpSecurityGate', () => ({
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
    expect(mockApiRequest).not.toHaveBeenCalled();
    expect(mockSetMCPConfigs).not.toHaveBeenCalled();
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
});
