import { describe, expect, it, vi, beforeEach, type Mock } from 'vitest';

import { gateMcpConfigBatch, gateMcpEnable, mcpConfigHasSecretRefs } from '@/hooks/useMcpSecurityGate';
import type { MCPServiceConfig } from '@/store/config/types';

vi.mock('@/services/llm-config', () => ({
  scanMCPConfig: vi.fn(),
  scanMCPConfigBatch: vi.fn(),
  validateMCPConfig: vi.fn(),
}));

import { scanMCPConfig, validateMCPConfig } from '@/services/llm-config';

const mockScanMCPConfig = scanMCPConfig as Mock;
const mockValidateMCPConfig = validateMCPConfig as Mock;

const filesystemConfig: MCPServiceConfig = {
  name: 'filesystem-tools',
  type: 'stdio',
  command: 'node',
  args: ['server.js'],
  description: 'Filesystem MCP',
  enabled: false,
};

describe('mcpConfigHasSecretRefs', () => {
  it('detects secret template in headers', () => {
    expect(
      mcpConfigHasSecretRefs({
        name: 'api',
        type: 'sse',
        url: 'https://mcp.example.com',
        command: '',
        args: [],
        description: 'test',
        enabled: false,
        headers: { Authorization: 'Bearer {{secret:KEY}}' },
      }),
    ).toBe(true);
  });
});

describe('gateMcpEnable', () => {
  beforeEach(() => {
    mockScanMCPConfig.mockReset();
    mockValidateMCPConfig.mockReset();
  });

  it('runs verify when no secret refs', async () => {
    mockScanMCPConfig.mockResolvedValue({
      serverName: 'docs',
      allowSave: true,
      requiresAcknowledgement: false,
      maxSeverity: 'low',
      findings: [],
    });
    mockValidateMCPConfig.mockResolvedValue({ success: true, latency: 12 });

    const config: MCPServiceConfig = {
      name: 'docs',
      type: 'sse',
      url: 'https://mcp.example.com/sse',
      command: '',
      args: [],
      description: 'Docs',
      enabled: false,
    };

    const result = await gateMcpEnable(config);
    expect(result.allowed).toBe(true);
    expect(mockValidateMCPConfig).toHaveBeenCalled();
  });

  it('skips verify when secret refs present', async () => {
    mockScanMCPConfig.mockResolvedValue({
      serverName: 'api',
      allowSave: true,
      requiresAcknowledgement: false,
      maxSeverity: 'low',
      findings: [],
    });

    const config: MCPServiceConfig = {
      name: 'api',
      type: 'sse',
      url: 'https://mcp.example.com/sse',
      command: '',
      args: [],
      description: 'API',
      enabled: false,
      headers: { Authorization: 'Bearer {{secret:KEY}}' },
    };

    const result = await gateMcpEnable(config);
    expect(result.allowed).toBe(true);
    expect(mockValidateMCPConfig).not.toHaveBeenCalled();
  });
});

describe('gateMcpConfigBatch', () => {
  beforeEach(() => {
    mockScanMCPConfig.mockReset();
  });

  it('returns needsAcknowledgement for high-risk single config', async () => {
    mockScanMCPConfig.mockResolvedValue({
      serverName: filesystemConfig.name,
      allowSave: true,
      requiresAcknowledgement: true,
      maxSeverity: 'high',
      findings: [{ threatType: 'risky_mcp_profile', severity: 'high', description: 'Filesystem', field: 'name' }],
    });

    const result = await gateMcpConfigBatch([filesystemConfig]);
    expect(result.blocked).toBeNull();
    expect(result.needsAcknowledgement?.config.name).toBe('filesystem-tools');
  });

  it('allows high-risk config when acknowledged', async () => {
    mockScanMCPConfig.mockResolvedValue({
      serverName: filesystemConfig.name,
      allowSave: true,
      requiresAcknowledgement: true,
      maxSeverity: 'high',
      findings: [],
    });

    const result = await gateMcpConfigBatch([filesystemConfig], true);
    expect(result.needsAcknowledgement).toBeNull();
    expect(result.scanResults).toHaveLength(1);
  });
});
