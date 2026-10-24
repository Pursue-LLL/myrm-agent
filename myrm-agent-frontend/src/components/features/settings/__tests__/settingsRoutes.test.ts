import { describe, expect, it } from 'vitest';
import {
  SETTINGS_TABS,
  SETTINGS_TAB_REDIRECTS,
  TAURI_ONLY_TABS,
  getSettingsTabRedirectPath,
  isSettingsTab,
} from '../settingsRoutes';

describe('settingsRoutes', () => {
  it('lists every tab id exactly once', () => {
    expect(new Set(SETTINGS_TABS).size).toBe(SETTINGS_TABS.length);
  });

  it('accepts tabs that the menu exposes but the old page whitelist missed', () => {
    expect(isSettingsTab('workbench')).toBe(true);
    expect(isSettingsTab('shares')).toBe(true);
    expect(isSettingsTab('brand-studio')).toBe(true);
  });

  it('rejects unknown ids and inherited object keys', () => {
    expect(isSettingsTab('browser')).toBe(false);
    expect(isSettingsTab('extensions')).toBe(false);
    expect(isSettingsTab('constructor')).toBe(false);
    expect(isSettingsTab('__proto__')).toBe(false);
  });

  it('keeps desktop-only tabs inside the known tab list', () => {
    for (const tab of TAURI_ONLY_TABS) {
      expect(isSettingsTab(tab)).toBe(true);
    }
  });

  it('redirects aliases straight to a canonical parent without chaining', () => {
    for (const [alias, { parent }] of Object.entries(SETTINGS_TAB_REDIRECTS)) {
      expect(isSettingsTab(parent), `${alias} -> ${parent}`).toBe(true);
      expect(SETTINGS_TAB_REDIRECTS[parent], `${alias} -> ${parent} must not chain`).toBeUndefined();
    }
  });

  it('builds the canonical redirect path with and without a sub view', () => {
    expect(getSettingsTabRedirectPath('defaultModel')).toBe('/settings/models?sub=default');
    expect(getSettingsTabRedirectPath('memory-cloud-backup')).toBe('/settings/memory?sub=cloud-backup');
    // 与侧栏子菜单 / 页内标签使用同一个 sub id（全小写），不是别名的驼峰写法。
    expect(getSettingsTabRedirectPath('importExport')).toBe('/settings/developer?sub=importexport');
    expect(getSettingsTabRedirectPath('persona')).toBe('/settings/personalization');
    expect(getSettingsTabRedirectPath('eval')).toBe('/settings/developer');
    // 质量页的旧链接落到工具稳定性页，而不是 404。
    expect(getSettingsTabRedirectPath('toolQuality')).toBe('/settings/toolStability');
    expect(getSettingsTabRedirectPath('skillQuality')).toBe('/settings/toolStability');
  });

  it('returns null for canonical tabs, unknown ids and inherited object keys', () => {
    expect(getSettingsTabRedirectPath('wiki')).toBeNull();
    expect(getSettingsTabRedirectPath('browser')).toBeNull();
    expect(getSettingsTabRedirectPath('constructor')).toBeNull();
    expect(getSettingsTabRedirectPath('toString')).toBeNull();
  });
});
