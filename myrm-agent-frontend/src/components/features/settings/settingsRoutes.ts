/**
 * [INPUT] 无外部业务模块依赖（纯常量与纯函数，可被 Node 脚本与后端架构测试按文本直接读取）
 * [OUTPUT] SETTINGS_TABS / SettingsTab: 全部可寻址的设置 Tab id; TAURI_ONLY_TABS: 仅桌面端展示的 Tab;
 *          SETTINGS_TAB_REDIRECTS / getSettingsTabRedirectPath: 别名路由到父级 Tab 的重定向表与解析; isSettingsTab: Tab id 类型守卫
 * [POS] 设置页路由单一信息源。服务端页面 `app/settings/[tab]/page.tsx`、`SettingsLayout`、`SettingsMenu`、
 *       `scripts/verify-i18n.mjs` 与后端深链架构测试共同读取；新增或下线设置 Tab 只改这里
 *       （其余登记点见 `sections/integration/_ARCH.md`）。
 */

/**
 * 全部可寻址的 Tab id。别名 id 中作为侧栏子菜单标签键（`SettingsMenu` 的 `labelKey`）的同样在列：
 * `settings.menu.<id>` 与页面标题由 `verify-i18n` 核对，`SettingsLayout` 的 Section 映射表也按此穷尽；
 * 仅作重定向入口的别名（`persona`、`toolCapabilities`、`eval`）不在此列。
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

interface SettingsTabRedirect {
  parent: SettingsTab;
  sub?: string;
}

/** 别名路由 → 父级 Tab（可带 `?sub=` 子视图）：这些页面是父级 Section 的子视图，访问时由服务端页面重定向。 */
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
  importExport: { parent: 'developer', sub: 'importexport' },
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
