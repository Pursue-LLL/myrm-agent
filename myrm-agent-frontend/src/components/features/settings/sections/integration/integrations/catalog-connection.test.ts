import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import useConfigStore from '@/store/useConfigStore';
import type { MCPServiceConfig } from '@/store/config/types';
import { resolveCatalogConnectionState, useCatalogConnectionState } from './catalog-connection';
import type { CatalogEntry } from './catalog-types';

function makeEntry(mcpConfig: CatalogEntry['mcpConfig']): CatalogEntry {
  return {
    id: 'notion',
    name: 'Notion',
    nameZh: 'Notion',
    description: 'Notes',
    descriptionZh: '笔记',
    icon: 'notion',
    category: 'productivity',
    connectorType: 'mcp',
    authType: 'api_key',
    helpUrl: null,
    helpText: null,
    helpTextZh: null,
    envKey: null,
    credentialFields: null,
    tags: [],
    website: null,
    mcpConfig,
    deploymentScope: 'all_modes',
    postConnectGuide: null,
    postConnectGuideZh: null,
  };
}

function makeConfig(name: string, enabled = true): MCPServiceConfig {
  return { name, type: 'stdio', description: '', enabled };
}

describe('resolveCatalogConnectionState', () => {
  const entry = makeEntry({ name: 'notion', type: 'stdio' });

  it('is available while the user holds no service under the template name', () => {
    expect(resolveCatalogConnectionState(entry, [])).toBe('available');
    expect(resolveCatalogConnectionState(entry, [makeConfig('github')])).toBe('available');
  });

  it('is connected once a service with the template name is saved and enabled', () => {
    expect(resolveCatalogConnectionState(entry, [makeConfig('github'), makeConfig('notion')])).toBe('connected');
  });

  it('is disabled when the saved service was switched off', () => {
    expect(resolveCatalogConnectionState(entry, [makeConfig('notion', false)])).toBe('disabled');
  });

  it('stays available for entries without a usable connection template', () => {
    const saved = [makeConfig('notion')];
    expect(resolveCatalogConnectionState(makeEntry(null), saved)).toBe('available');
    expect(resolveCatalogConnectionState(makeEntry({ type: 'stdio' }), saved)).toBe('available');
    expect(resolveCatalogConnectionState(makeEntry({ name: 42 }), saved)).toBe('available');
  });
});

describe('useCatalogConnectionState', () => {
  beforeEach(() => {
    useConfigStore.setState({ mcpConfigs: [] });
  });

  it('follows the saved MCP services as they change', () => {
    const entry = makeEntry({ name: 'notion', type: 'stdio' });
    const { result } = renderHook(() => useCatalogConnectionState());
    expect(result.current(entry)).toBe('available');

    act(() => useConfigStore.setState({ mcpConfigs: [makeConfig('notion')] }));
    expect(result.current(entry)).toBe('connected');

    act(() => useConfigStore.setState({ mcpConfigs: [makeConfig('notion', false)] }));
    expect(result.current(entry)).toBe('disabled');
  });
});
