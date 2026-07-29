/**
 * Search priority chain config helpers
 */

import { describe, it, expect } from 'vitest';
import {
  migrateSearchConfigItem,
  normalizeSearchServiceConfigs,
  enableSearchServiceConfig,
  suggestNextPriority,
  getActiveSearchServiceConfig,
} from '@/store/config/searchService';
import type { SearchServiceConfigItem } from '@/store/config/types';

function checkPriorityConflict(
  searchServiceConfigs: SearchServiceConfigItem[],
  currentConfig: SearchServiceConfigItem | null,
  newPriority: number,
): boolean {
  if (!currentConfig?.enabled) {
    return false;
  }
  const existingConfigs = searchServiceConfigs.filter((c) => c.id !== currentConfig?.id);
  return existingConfigs.some((c) => c.priority === newPriority && c.enabled);
}

describe('search priority chain', () => {
  it('migrates legacy role to priority', () => {
    const migrated = migrateSearchConfigItem({
      id: 'a',
      enabled: true,
      role: 'fallback',
      search_service: 'searxng',
      priority: 0,
      createdAt: 1,
    });
    expect(migrated.priority).toBe(2);
  });

  it('detects priority conflict for enabled configs', () => {
    const p1: SearchServiceConfigItem = {
      id: 'a',
      enabled: true,
      priority: 1,
      search_service: 'tavily',
      createdAt: 1,
    };
    const p2: SearchServiceConfigItem = {
      id: 'b',
      enabled: true,
      priority: 2,
      search_service: 'searxng',
      createdAt: 2,
    };
    expect(checkPriorityConflict([p1, p2], p1, 2)).toBe(true);
    expect(checkPriorityConflict([p1, p2], p1, 3)).toBe(false);
  });

  it('enable disables same-priority config', () => {
    const configs: SearchServiceConfigItem[] = [
      { id: 'a', enabled: true, priority: 1, search_service: 'tavily', createdAt: 1 },
      { id: 'b', enabled: false, priority: 1, search_service: 'searxng', createdAt: 2 },
    ];
    const next = enableSearchServiceConfig(configs, 'b');
    expect(next.find((c) => c.id === 'a')?.enabled).toBe(false);
    expect(next.find((c) => c.id === 'b')?.enabled).toBe(true);
  });

  it('suggests next free priority', () => {
    const configs: SearchServiceConfigItem[] = [
      { id: 'a', enabled: true, priority: 1, search_service: 'tavily', createdAt: 1 },
      { id: 'b', enabled: true, priority: 2, search_service: 'searxng', createdAt: 2 },
    ];
    expect(suggestNextPriority(configs)).toBe(3);
  });

  it('returns head of enabled chain', () => {
    const configs = normalizeSearchServiceConfigs([
      { id: 'a', enabled: true, priority: 2, search_service: 'perplexity', api_key: 'k', createdAt: 1 },
      { id: 'b', enabled: true, priority: 1, search_service: 'tavily', api_key: 'k1', createdAt: 2 },
    ]);
    const active = getActiveSearchServiceConfig(configs);
    expect(active?.search_service).toBe('tavily');
  });
});
