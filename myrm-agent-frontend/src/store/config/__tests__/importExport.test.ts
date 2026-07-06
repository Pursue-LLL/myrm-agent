import { describe, it, expect, vi } from 'vitest';

vi.mock('@/hooks/useMcpSecurityGate', () => ({
  gateMcpConfigBatch: vi.fn(async () => ({
    blocked: null,
    scanResults: [],
    needsAcknowledgement: null,
  })),
}));

import { exportConfig, importConfig } from '../importExport';

describe('exportConfig', () => {
  it('should export config with version and timestamp', () => {
    const result = exportConfig({ systemInstructions: 'test' });
    const parsed = JSON.parse(result);

    expect(parsed.version).toBe('4.0.0');
    expect(parsed.timestamp).toBeDefined();
    expect(parsed.config.systemInstructions).toBe('test');
  });

  it('should include provider state when provided', () => {
    const result = exportConfig(
      { systemInstructions: 'test' },
      {
        providers: [
          {
            id: 'openai',
            name: 'OpenAI',
            providerType: 'openai',
            isEnabled: true,
            apiKeys: [{ key: 'sk-xxx', isActive: true }],
            models: ['gpt-4'],
            apiUrl: '',
          } as never,
        ],
      },
    );
    const parsed = JSON.parse(result);

    expect(parsed.config.providers).toHaveLength(1);
    expect(parsed.config.providers[0].id).toBe('openai');
  });
});

describe('importConfig', () => {
  it('should import valid config and call setters', async () => {
    const setSystemInstructions = vi.fn();
    const setFetchRawWebpage = vi.fn();

    const json = JSON.stringify({
      config: {
        systemInstructions: 'New prompt',
        fetchRawWebpage: true,
      },
    });

    const result = await importConfig(json, {
      setSystemInstructions,
      setFetchRawWebpage,
    });

    expect(result.success).toBe(true);
    expect(result.messageKey).toBe('importSuccess');
    expect(setSystemInstructions).toHaveBeenCalledWith('New prompt');
    expect(setFetchRawWebpage).toHaveBeenCalledWith(true);
  });

  it('should only call provided setters', async () => {
    const setSystemInstructions = vi.fn();

    const json = JSON.stringify({
      config: {
        systemInstructions: 'Test',
        fetchRawWebpage: true,
      },
    });

    await importConfig(json, { setSystemInstructions });

    expect(setSystemInstructions).toHaveBeenCalledWith('Test');
  });

  it('should return error for missing config field', async () => {
    const json = JSON.stringify({ version: '4.0.0' });
    const result = await importConfig(json, {});

    expect(result.success).toBe(false);
    expect(result.messageKey).toBe('invalidFormat');
  });

  it('should return error for invalid JSON', async () => {
    const result = await importConfig('not json!!', {});

    expect(result.success).toBe(false);
    expect(result.messageKey).toBe('parseError');
  });

  it('should import arrays correctly', async () => {
    const setSearchServiceConfigs = vi.fn();
    const setMCPConfigs = vi.fn();
    const setProviders = vi.fn();

    const configs = [{ id: '1', enabled: true, role: 'primary', search_service: 'tavily', createdAt: 1 }];
    const mcps = [{ name: 'test', type: 'sse', url: 'http://test.com' }];
    const providers = [{ id: 'test', name: 'Test' }];

    const json = JSON.stringify({
      config: {
        searchServiceConfigs: configs,
        mcpConfigs: mcps,
        providers: providers,
      },
    });

    await importConfig(json, {
      setSearchServiceConfigs,
      setMCPConfigs,
      setProviders,
    });

    expect(setSearchServiceConfigs).toHaveBeenCalledWith(configs);
    expect(setMCPConfigs).toHaveBeenCalledWith(mcps);
    expect(setProviders).toHaveBeenCalledWith([{ id: 'test', name: 'Test', routingProfile: 'test' }]);
  });

  it('should not call setter when value is undefined in config', async () => {
    const setSystemInstructions = vi.fn();

    const json = JSON.stringify({ config: {} });
    await importConfig(json, { setSystemInstructions });

    expect(setSystemInstructions).not.toHaveBeenCalled();
  });

  it('should migrate legacy providerType values without throwing', async () => {
    const setProviders = vi.fn();

    const json = JSON.stringify({
      config: {
        providers: [
          {
            id: 'legacy_gateway',
            name: 'Legacy Gateway',
            providerType: 'openai',
            isBuiltIn: false,
            isEnabled: false,
            apiKeys: [],
            apiUrl: 'https://api.example.com/v1',
            enabledModels: [],
            availableModels: [],
          },
        ],
      },
    });

    const result = await importConfig(json, { setProviders });

    expect(result.success).toBe(true);
    expect(setProviders).toHaveBeenCalledWith([
      expect.objectContaining({
        id: 'legacy_gateway',
        routingProfile: 'legacy_gateway',
        providerType: 'openai',
      }),
    ]);
  });
});
