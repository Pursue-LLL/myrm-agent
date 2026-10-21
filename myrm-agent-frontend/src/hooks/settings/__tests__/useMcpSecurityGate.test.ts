import { describe, expect, it, vi, beforeEach, type Mock } from 'vitest';

import { gateMcpConfigBatch, gateMcpEnable, mcpConfigHasSecretRefs } from '@/hooks/settings/useMcpSecurityGate';
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

describe('mcpConfigHelpers', () => {
  it('validates form fields, parses args, and runs parallel status checks', async () => {
    const {
      DEFAULT_FORM_DATA,
      buildConnectionTypeOptions,
      buildImportPlaceholder,
      buildInitialMcpStatusMap,
      parseFinalFormData,
      runParallelMcpStatusValidation,
      scheduleDebouncedLiveScan,
      validateMCPFormFields,
    } = await import('@/hooks/settings/mcpConfigHelpers');

    const t = (k: string) => k;

    expect(buildConnectionTypeOptions(null)).toHaveLength(3);
    expect(
      buildConnectionTypeOptions({
        allowStdio: false,
        allowSse: true,
        allowedTypes: ['sse', 'streamable_http'],
        requireHttps: true,
        ssrfProtectionEnabled: true,
        verifyTimeout: 30,
      }).map((o) => o.value),
    ).toEqual(['sse', 'streamable_http']);

    expect(buildImportPlaceholder(true, t)).toContain('mcpImportDescription');
    expect(buildImportPlaceholder(false, t)).toContain('mcpImportDescriptionSandbox');

    const parsedJson = parseFinalFormData(
      { ...DEFAULT_FORM_DATA, type: 'stdio', command: 'npx' },
      '["-y", "demo"]',
      t,
    );
    expect(parsedJson.data?.args).toEqual(['-y', 'demo']);

    const parsedObjLine = parseFinalFormData(
      { ...DEFAULT_FORM_DATA, type: 'stdio', command: 'npx' },
      '{"a":1}',
      t,
    );
    expect(parsedObjLine.data?.args).toEqual(['{"a":1}']);


    const parsedBadJson = parseFinalFormData(
      { ...DEFAULT_FORM_DATA, type: 'stdio', command: 'npx' },
      '[bad]',
      t,
    );
    expect(parsedBadJson.data).toBeNull();
    expect(parsedBadJson.error).toContain('mcpArgsErrorParse');


    const parsedLines = parseFinalFormData(
      { ...DEFAULT_FORM_DATA, type: 'stdio', command: 'npx' },
      '-y\ndemo\n',
      t,
    );
    expect(parsedLines.data?.args).toEqual(['-y', 'demo']);

    const parsedSse = parseFinalFormData(
      { ...DEFAULT_FORM_DATA, type: 'sse', url: 'https://example.com/sse', keepaliveInterval: 15 },
      'a\nb',
      t,
    );
    expect(parsedSse.data?.keepaliveInterval).toBe(15);

    const errs1 = validateMCPFormFields(
      { ...DEFAULT_FORM_DATA, type: 'sse', url: 'not-a-url', keepaliveInterval: 2 },
      t,
    );
    expect(errs1.name).toBe('mcpNameRequired');
    expect(errs1.url).toBe('mcpUrlInvalid');
    expect(errs1.keepaliveInterval).toBe('mcpKeepaliveIntervalMin');
    expect(errs1.description).toBe('mcpDescriptionRequired');

    const errs2 = validateMCPFormFields(
      { ...DEFAULT_FORM_DATA, name: 'ok', description: 'ok', type: 'stdio', command: '' },
      t,
    );
    expect(errs2.command).toBe('mcpCommandRequired');

    const cfgs: MCPServiceConfig[] = [
      { ...DEFAULT_FORM_DATA, name: 's1', enabled: true, url: 'https://a.com' },
      { ...DEFAULT_FORM_DATA, name: 's2', enabled: false, url: 'https://b.com' },
      {
        ...DEFAULT_FORM_DATA,
        name: 's3',
        enabled: true,
        url: 'https://c.com',
        headers: { Authorization: 'Bearer {{secret:TOK}}' },
      },
      { ...DEFAULT_FORM_DATA, name: 's4', enabled: true, url: 'https://d.com' },
    ];
    const initMap = buildInitialMcpStatusMap(cfgs);
    expect(initMap.s1.pending).toBe(true);
    expect(initMap.s2.available).toBe(false);

    const updates: Record<string, { available: boolean; latency?: number }> = {};
    await runParallelMcpStatusValidation(
      cfgs,
      async (cfg) => {
        if (cfg.name === 's4') {
          throw new Error('network');
        }
        return { success: true, latency: 42 };
      },
      (name, status) => {
        updates[name] = status;
      },
      () => false,
    );
    expect(updates.s1).toEqual({ available: true, latency: 42 });
    expect(updates.s2).toBeUndefined();
    expect(updates.s3).toEqual({ available: true });
    expect(updates.s4).toEqual({ available: false });

    const reqRef = { current: 0 };
    const findingsOut: unknown[] = [];
    expect(
      scheduleDebouncedLiveScan(
        { ...DEFAULT_FORM_DATA, name: '' },
        reqRef,
        async () => ({ findings: [] }),
        (f) => findingsOut.push(f),
        () => {},
      ),
    ).toBeUndefined();

    const cleanup = scheduleDebouncedLiveScan(
      { ...DEFAULT_FORM_DATA, name: 'live' },
      reqRef,
      async () => ({ findings: [] }),
      (f) => findingsOut.push(f),
      () => {},
    );
    expect(typeof cleanup).toBe('function');
    cleanup?.();
  });
});

