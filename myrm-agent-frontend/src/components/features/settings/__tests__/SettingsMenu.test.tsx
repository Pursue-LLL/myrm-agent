/**
 * SettingsMenu 组件测试
 *
 * 测试核心逻辑：搜索高亮、分组、过滤
 */

import { describe, it, expect } from 'vitest';

/** 复刻 SettingsMenu 中的 highlightMatch 函数 */
function highlightMatch(text: string, query: string): string {
  if (!query.trim()) return text;
  const idx = text.toLowerCase().indexOf(query.toLowerCase());
  if (idx === -1) return text;
  return text.slice(0, idx) + `[HL]${text.slice(idx, idx + query.length)}[/HL]` + text.slice(idx + query.length);
}

/** 复刻 SettingsMenu 中的分组逻辑 */
type SettingsGroup = 'personal' | 'ai-core' | 'ai-tools' | 'knowledge' | 'integration' | 'system';

interface MenuItem {
  id: string;
  labelKey: string;
  group: SettingsGroup;
  tauriOnly?: boolean;
  adminOnly?: boolean;
}

const groupConfig: Record<SettingsGroup, { order: number }> = {
  personal: { order: 1 },
  'ai-core': { order: 2 },
  'ai-tools': { order: 3 },
  knowledge: { order: 4 },
  integration: { order: 5 },
  system: { order: 6 },
};

function groupItems(items: MenuItem[]): Map<SettingsGroup, MenuItem[]> {
  const groups = new Map<SettingsGroup, MenuItem[]>();
  items.forEach((item) => {
    if (!groups.has(item.group)) groups.set(item.group, []);
    groups.get(item.group)!.push(item);
  });
  return new Map(
    Array.from(groups.entries())
      .filter(([, groupItems]) => groupItems.length > 0)
      .sort(([a], [b]) => groupConfig[a].order - groupConfig[b].order),
  );
}

function filterVisible(items: MenuItem[], tauriMode: boolean, isAdmin: boolean): MenuItem[] {
  return items.filter((item) => {
    if (item.tauriOnly && !tauriMode) return false;
    if (item.adminOnly && !isAdmin) return false;
    return true;
  });
}

describe('SettingsMenu - highlightMatch', () => {
  it('should return original text when query is empty', () => {
    expect(highlightMatch('Model Service', '')).toBe('Model Service');
    expect(highlightMatch('Model Service', '   ')).toBe('Model Service');
  });

  it('should highlight matching text (case-insensitive)', () => {
    expect(highlightMatch('Model Service', 'model')).toBe('[HL]Model[/HL] Service');
    expect(highlightMatch('Model Service', 'MODEL')).toBe('[HL]Model[/HL] Service');
    expect(highlightMatch('Model Service', 'service')).toBe('Model [HL]Service[/HL]');
  });

  it('should return original text when no match', () => {
    expect(highlightMatch('Model Service', 'agent')).toBe('Model Service');
  });

  it('should highlight partial match', () => {
    expect(highlightMatch('Security Policy', 'secur')).toBe('[HL]Secur[/HL]ity Policy');
  });

  it('should handle full match', () => {
    expect(highlightMatch('MCP', 'MCP')).toBe('[HL]MCP[/HL]');
  });
});

describe('SettingsMenu - groupItems', () => {
  const sampleItems: MenuItem[] = [
    { id: 'account', labelKey: 'account', group: 'personal' },
    { id: 'models', labelKey: 'models', group: 'ai-core' },
    { id: 'agents', labelKey: 'agents', group: 'ai-core' },
    { id: 'mcp', labelKey: 'mcp', group: 'ai-tools' },
    { id: 'system', labelKey: 'system', group: 'system' },
  ];

  it('should group items correctly', () => {
    const groups = groupItems(sampleItems);
    expect(groups.size).toBe(4);
    expect(groups.get('personal')?.length).toBe(1);
    expect(groups.get('ai-core')?.length).toBe(2);
    expect(groups.get('ai-tools')?.length).toBe(1);
    expect(groups.get('system')?.length).toBe(1);
  });

  it('should sort groups by order', () => {
    const groups = groupItems(sampleItems);
    const keys = Array.from(groups.keys());
    expect(keys).toEqual(['personal', 'ai-core', 'ai-tools', 'system']);
  });

  it('should filter out empty groups', () => {
    const items: MenuItem[] = [{ id: 'account', labelKey: 'account', group: 'personal' }];
    const groups = groupItems(items);
    expect(groups.size).toBe(1);
    expect(groups.has('ai-core')).toBe(false);
  });
});

describe('SettingsMenu - filterVisible', () => {
  const items: MenuItem[] = [
    { id: 'account', labelKey: 'account', group: 'personal' },
    { id: 'channels', labelKey: 'channels', group: 'integration', tauriOnly: true },
    { id: 'voice', labelKey: 'voice', group: 'integration', tauriOnly: true },
    { id: 'admin', labelKey: 'admin', group: 'system', adminOnly: true },
  ];

  it('should hide tauriOnly items when not in tauri mode', () => {
    const visible = filterVisible(items, false, false);
    expect(visible.length).toBe(1);
    expect(visible[0].id).toBe('account');
    expect(visible.find((i) => i.id === 'channels')).toBeUndefined();
    expect(visible.find((i) => i.id === 'voice')).toBeUndefined();
    expect(visible.find((i) => i.id === 'admin')).toBeUndefined();
  });

  it('should show tauriOnly items in tauri mode', () => {
    const visible = filterVisible(items, true, false);
    expect(visible.length).toBe(3);
    expect(visible.find((i) => i.id === 'channels')).toBeDefined();
    expect(visible.find((i) => i.id === 'voice')).toBeDefined();
  });

  it('should hide adminOnly items for non-admin', () => {
    const visible = filterVisible(items, false, false);
    expect(visible.find((i) => i.id === 'admin')).toBeUndefined();
  });

  it('should show adminOnly items for admin', () => {
    const visible = filterVisible(items, false, true);
    expect(visible.find((i) => i.id === 'admin')).toBeDefined();
  });

  it('should show all items for admin in tauri mode', () => {
    const visible = filterVisible(items, true, true);
    expect(visible.length).toBe(4);
    expect(visible.find((i) => i.id === 'channels')).toBeDefined();
    expect(visible.find((i) => i.id === 'admin')).toBeDefined();
  });
});

describe('SettingsMenu - search filtering', () => {
  const labels: Record<string, string> = {
    account: 'Account',
    models: 'Model Service',
    agents: 'Agents',
    mcp: 'MCP',
    security: 'Security Policy',
  };

  function searchItems(items: MenuItem[], query: string): MenuItem[] {
    if (!query.trim()) return items;
    const q = query.toLowerCase();
    return items.filter((item) => labels[item.labelKey]?.toLowerCase().includes(q));
  }

  const items: MenuItem[] = [
    { id: 'account', labelKey: 'account', group: 'personal' },
    { id: 'models', labelKey: 'models', group: 'ai-core' },
    { id: 'agents', labelKey: 'agents', group: 'ai-core' },
    { id: 'mcp', labelKey: 'mcp', group: 'ai-tools' },
    { id: 'security', labelKey: 'security', group: 'security' },
  ];

  it('should return all items when query is empty', () => {
    expect(searchItems(items, '').length).toBe(5);
    expect(searchItems(items, '   ').length).toBe(5);
  });

  it('should filter by label (case-insensitive)', () => {
    expect(searchItems(items, 'model').length).toBe(1);
    expect(searchItems(items, 'MODEL').length).toBe(1);
  });

  it('should return empty for no match', () => {
    expect(searchItems(items, 'xyz').length).toBe(0);
  });

  it('should match partial text', () => {
    expect(searchItems(items, 'sec').length).toBe(1);
    expect(searchItems(items, 'agent').length).toBe(1);
  });
});
