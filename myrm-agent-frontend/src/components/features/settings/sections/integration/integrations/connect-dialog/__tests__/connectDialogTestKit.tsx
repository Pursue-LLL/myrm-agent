import { vi } from 'vitest';

import type { MCPServiceConfig } from '@/store/config/types';
import type { CatalogEntry } from '../../catalog-types';

/**
 * Shared doubles and fixtures for the connect-dialog flow suites.
 *
 * `vi.mock` registrations stay in each test file (they are hoisted per file) and hand back the
 * `*Mock` module objects below through an async factory, so every suite shares one set of `vi.fn`s.
 */

export const mockApiRequest = vi.fn();
export const mockSetMCPConfigs = vi.fn();
export const mockGateMcpEnable = vi.fn();
export const mockToast = vi.fn();
export const mockIsSandbox = vi.fn();
export const storeState: { mcpConfigs: MCPServiceConfig[] } = { mcpConfigs: [] };

export const SCAN_SUMMARY = { maxSeverity: null, scannedAt: 1, findingCount: 0 };
export const GATE_ALLOWED = {
  needsAcknowledgement: false,
  allowed: true,
  scanResult: { findings: [] },
  verifyError: null,
  verifyFindings: [],
};

const stableT = (key: string) => key;

interface ScanAckDialogStubProps {
  open: boolean;
  serverName: string;
  findings: unknown[];
  onConfirm: () => void;
  onCancel: () => void;
}

function ScanAckDialogStub({ open, serverName, findings, onConfirm, onCancel }: ScanAckDialogStubProps) {
  if (!open) {
    return null;
  }
  return (
    <div data-testid="scan-ack">
      <span data-testid="scan-ack-server">{serverName}</span>
      <span data-testid="scan-ack-findings">{findings.length}</span>
      <button type="button" onClick={onConfirm}>
        ack-confirm
      </button>
      <button type="button" onClick={onCancel}>
        ack-cancel
      </button>
    </div>
  );
}

export const nextIntlMock = { useTranslations: () => stableT };
export const toastMock = { toast: (...args: unknown[]) => mockToast(...args) };
export const configStoreMock = {
  default: () => ({ mcpConfigs: storeState.mcpConfigs, setMCPConfigs: mockSetMCPConfigs }),
};
export const apiMock = {
  apiRequest: (...args: unknown[]) => mockApiRequest(...args),
};
export const securityGateMock = {
  buildLastScanSummary: () => SCAN_SUMMARY,
  gateMcpEnable: (...args: unknown[]) => mockGateMcpEnable(...args),
};
export const mcpConfigUtilsMock = { formatMcpGateBlockedMessage: () => 'blocked' };
export const scanAckDialogMock = { MCPScanAckDialog: ScanAckDialogStub };
export const deployModeMock = {
  isSandbox: () => mockIsSandbox(),
  getDocsUrl: (path: string = '/') => `https://docs.myrm.ai${path === '/' ? '' : path}`,
};

export function resetConnectDialogMocks() {
  mockApiRequest.mockReset();
  mockSetMCPConfigs.mockReset();
  mockGateMcpEnable.mockReset();
  mockGateMcpEnable.mockResolvedValue(GATE_ALLOWED);
  mockToast.mockReset();
  mockIsSandbox.mockReset();
  mockIsSandbox.mockReturnValue(false);
  storeState.mcpConfigs = [];
}

export function restoreConnectDialogGlobals() {
  vi.restoreAllMocks();
}

export function makeEntry(overrides?: Partial<CatalogEntry>): CatalogEntry {
  return {
    id: 'svc',
    name: 'Svc',
    nameZh: 'Svc',
    description: 'Service',
    descriptionZh: '服务',
    icon: 'svc',
    category: 'dev',
    connectorType: 'mcp',
    authType: 'api_key',
    helpUrl: null,
    helpText: null,
    helpTextZh: null,
    envKey: 'SVC_TOKEN',
    credentialFields: null,
    tags: [],
    website: null,
    mcpConfig: {
      name: 'svc',
      type: 'stdio',
      command: 'npx',
      args: ['-y', 'svc-mcp'],
      env: { BASE: '1' },
      description: 'Svc MCP',
    },
    deploymentScope: 'all_modes',
    postConnectGuide: null,
    postConnectGuideZh: null,
    ...overrides,
  };
}

export function makeStoredConfig(name: string): MCPServiceConfig {
  return { name, type: 'stdio', description: '', enabled: true };
}
