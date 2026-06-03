import { describe, it, expect } from 'vitest';
import { parseImportJson } from '../ImportPreviewDialog';

describe('parseImportJson', () => {
  it('should parse valid config with all categories', () => {
    const json = JSON.stringify({
      version: '4.0.0',
      timestamp: '2026-04-27T00:00:00.000Z',
      config: {
        systemInstructions: 'You are a helpful assistant',
        fetchRawWebpage: true,
        generateSearchSuggestions: false,
        enableCostEstimation: true,
        searchServiceConfigs: [{ id: '1', enabled: true, role: 'primary', search_service: 'tavily', createdAt: 1 }],
        mcpConfigs: [{ name: 'test-mcp', type: 'sse', url: 'http://example.com' }],
        providers: [
          {
            id: 'openai',
            name: 'OpenAI',
            providerType: 'openai',
            isEnabled: true,
            apiKeys: [],
            models: [],
            apiUrl: '',
          },
        ],
        defaultModelConfig: { baseModel: { primary: { providerId: 'openai', model: 'gpt-4' } } },
        customModelInfo: { 'openai/gpt-4': { supports_vision: true } },
      },
    });

    const result = parseImportJson(json);
    expect('error' in result).toBe(false);
    if (!('error' in result)) {
      expect(result.version).toBe('4.0.0');
      expect(result.timestamp).toBe('2026-04-27T00:00:00.000Z');
      expect(result.availableCategories.size).toBe(7);
      expect(result.availableCategories.has('systemInstructions')).toBe(true);
      expect(result.availableCategories.has('generalSettings')).toBe(true);
      expect(result.availableCategories.has('searchServices')).toBe(true);
      expect(result.availableCategories.has('mcpServices')).toBe(true);
      expect(result.availableCategories.has('providers')).toBe(true);
      expect(result.availableCategories.has('defaultModel')).toBe(true);
      expect(result.availableCategories.has('customModelInfo')).toBe(true);
    }
  });

  it('should parse config with partial categories', () => {
    const json = JSON.stringify({
      version: '4.0.0',
      config: {
        systemInstructions: 'Test prompt',
        providers: [
          {
            id: 'anthropic',
            name: 'Anthropic',
            providerType: 'anthropic',
            isEnabled: true,
            apiKeys: [],
            models: [],
            apiUrl: '',
          },
        ],
      },
    });

    const result = parseImportJson(json);
    expect('error' in result).toBe(false);
    if (!('error' in result)) {
      expect(result.availableCategories.size).toBe(2);
      expect(result.availableCategories.has('systemInstructions')).toBe(true);
      expect(result.availableCategories.has('providers')).toBe(true);
      expect(result.availableCategories.has('searchServices')).toBe(false);
    }
  });

  it('should return error for invalid format (missing config)', () => {
    const json = JSON.stringify({ version: '4.0.0', data: {} });
    const result = parseImportJson(json);
    expect('error' in result).toBe(true);
    if ('error' in result) {
      expect(result.error).toBe('invalidFormat');
    }
  });

  it('should return error for invalid JSON', () => {
    const result = parseImportJson('not valid json{{{');
    expect('error' in result).toBe(true);
    if ('error' in result) {
      expect(result.error).toBe('parseError');
    }
  });

  it('should handle empty config object', () => {
    const json = JSON.stringify({ version: '4.0.0', config: {} });
    const result = parseImportJson(json);
    expect('error' in result).toBe(false);
    if (!('error' in result)) {
      expect(result.availableCategories.size).toBe(0);
    }
  });

  it('should detect generalSettings from individual boolean fields', () => {
    const json = JSON.stringify({
      version: '4.0.0',
      config: { fetchRawWebpage: true },
    });

    const result = parseImportJson(json);
    expect('error' in result).toBe(false);
    if (!('error' in result)) {
      expect(result.availableCategories.has('generalSettings')).toBe(true);
      expect(result.availableCategories.size).toBe(1);
    }
  });

  it('should not detect empty arrays as available categories', () => {
    const json = JSON.stringify({
      version: '4.0.0',
      config: {
        searchServiceConfigs: [],
        mcpConfigs: [],
        providers: [],
      },
    });

    const result = parseImportJson(json);
    expect('error' in result).toBe(false);
    if (!('error' in result)) {
      expect(result.availableCategories.has('searchServices')).toBe(false);
      expect(result.availableCategories.has('mcpServices')).toBe(false);
      expect(result.availableCategories.has('providers')).toBe(false);
    }
  });
});
