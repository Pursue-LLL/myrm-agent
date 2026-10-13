/**
 * 设置页路由单一信息源：`/settings/[tab]` 的合法 id、历史别名重定向、仅桌面端 Tab。
 *
 * 服务端页面 `app/settings/[tab]/page.tsx`、`SettingsLayout`、`SettingsMenu`、
 * `scripts/verify-i18n.mjs` 与后端深链架构测试共同读取本文件；新增或下线设置 Tab 只改这里
 * （其余登记点见 `sections/integration/_ARCH.md`）。
 */

/**
 * 全部已知 Tab id。别名 id（见 `SETTINGS_TAB_REDIRECTS`）同样在列：
 * 侧栏子视图以 `settings.menu.<id>` 作标签，`SettingsLayout` 的 Section 映射表也按此穷尽。
 */
export const SETTINGS_TABS = [
  'account',
  'workbench',
  'preferences',
  'theme-studio',
  'personalization',
  'agents',
  'security',
  'riskRules',
  'shares',
  'models',
  'defaultModel',
  'search',
  'mcp',
  'skills',
  'skillQuality',
  'toolStability',
  'toolQuality',
  'evolutionPending',
  'evolutionRejection',
  'credentials',
  'wiki',
  'openaiApi',
  'hosting',
  'developer',
  'importExport',
  'cron',
  'kanban',
  'checkpoint',
  'channels',
  'channelRouting',
  'voice',
  'companion',
  'usageStatistics',
  'experimentalFeatures',
  'memory',
  'brand-studio',
  'memory-backup',
  'memory-cloud-backup',
  'memory-migration',
  'integrationCatalog',
  'integrationMemory',
  'extensionBridge',
  'connect',
  'a2aPeers',
  'workspaceRules',
  'enterprise',
  'system',
  'about',
] as const;

export type SettingsTab = (typeof SETTINGS_TABS)[number];

/** 仅桌面端（Tauri）展示；其他部署形态访问时回落到默认 Tab。 */
export const TAURI_ONLY_TABS: readonly SettingsTab[] = ['channels', 'channelRouting', 'voice'];

export interface SettingsTabRedirect {
  parent: SettingsTab;
  sub?: string;
}

/** 已并入父级 Section 的历史扁平路由 → 父级 Tab（可带 `?sub=` 子视图）。 */
export const SETTINGS_TAB_REDIRECTS: Readonly<Record<string, SettingsTabRedirect>> = {
  persona: { parent: 'personalization' },
  toolCapabilities: { parent: 'models' },
  defaultModel: { parent: 'models', sub: 'default' },
  evolutionPending: { parent: 'skills', sub: 'pending' },
  evolutionRejection: { parent: 'skills', sub: 'rejections' },
  skillQuality: { parent: 'toolQuality', sub: 'quality' },
  toolStability: { parent: 'toolQuality', sub: 'stability' },
  'memory-backup': { parent: 'memory', sub: 'backup' },
  'memory-cloud-backup': { parent: 'memory', sub: 'cloud-backup' },
  'memory-migration': { parent: 'memory', sub: 'migration' },
  channelRouting: { parent: 'channels', sub: 'routing' },
  voice: { parent: 'channels', sub: 'voice' },
  experimentalFeatures: { parent: 'developer', sub: 'experimental' },
  usageStatistics: { parent: 'developer', sub: 'usage' },
  companion: { parent: 'developer', sub: 'companion' },
  importExport: { parent: 'developer', sub: 'importExport' },
  eval: { parent: 'developer' },
  about: { parent: 'system', sub: 'about' },
};

const SETTINGS_TAB_SET: ReadonlySet<string> = new Set(SETTINGS_TABS);

export function isSettingsTab(value: string): value is SettingsTab {
  return SETTINGS_TAB_SET.has(value);
}

/** 别名路由对应的规范路径；非别名返回 `null`。 */
export function getSettingsTabRedirectPath(tab: string): string | null {
  if (!Object.prototype.hasOwnProperty.call(SETTINGS_TAB_REDIRECTS, tab)) {
    return null;
  }
  const { parent, sub } = SETTINGS_TAB_REDIRECTS[tab];
  return `/settings/${parent}${sub ? `?sub=${sub}` : ''}`;
}
