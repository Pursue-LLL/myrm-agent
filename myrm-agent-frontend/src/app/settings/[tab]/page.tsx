import { Suspense } from 'react';
import { notFound, redirect } from 'next/navigation';
import SettingsLayout from '@/components/ui/settings/SettingsLayout';
import { getTranslations } from 'next-intl/server';

const SettingsLoading = () => (
  <div className="flex items-center justify-center min-h-[50vh]">
    <div className="animate-spin w-8 h-8 border-2 border-primary border-t-transparent rounded-full" />
  </div>
);

// 有效的 tab 列表
const VALID_TABS = [
  'account',
  'preferences',
  'personalization',
  'persona',
  'agents',
  'security',
  'riskRules',
  'models',
  'defaultModel',
  'search',
  'mcp',
  'skills',
  'toolCapabilities',
  'skillQuality',
  'toolStability',
  'toolQuality',
  'evolutionPending',
  'evolutionRejection',
  'eval',
  'credentials',
  'wiki',
  'localFileSearch',
  'memory',
  'cron',
  'kanban',
  'checkpoint',
  'channels',
  'channelRouting',
  'voice',
  'openaiApi',
  'integrationCatalog',
  'workspaceRules',
  'developer',
  'importExport',
  'companion',
  'usageStatistics',
  'experimentalFeatures',
  'memory-backup',
  'memory-archival',
  'system',
  'about',
] as const;

const DEPRECATED_TAB_MAP: Record<string, { parent: string; sub?: string }> = {
  defaultModel: { parent: 'models', sub: 'default' },
  evolutionPending: { parent: 'skills', sub: 'pending' },
  evolutionRejection: { parent: 'skills', sub: 'rejections' },
  skillQuality: { parent: 'toolQuality', sub: 'quality' },
  toolStability: { parent: 'toolQuality', sub: 'stability' },
  'memory-backup': { parent: 'memory', sub: 'backup' },
  'memory-archival': { parent: 'memory', sub: 'archival' },
  channelRouting: { parent: 'channels', sub: 'routing' },
  voice: { parent: 'channels', sub: 'voice' },
  experimentalFeatures: { parent: 'developer', sub: 'experimental' },
  usageStatistics: { parent: 'developer', sub: 'usage' },
  companion: { parent: 'developer', sub: 'companion' },
  importExport: { parent: 'developer', sub: 'importExport' },
  about: { parent: 'system', sub: 'about' },
};

type ValidTab = (typeof VALID_TABS)[number];

interface PageProps {
  params: Promise<{
    tab: string;
  }>;
}

/**
 * 生成静态参数（预渲染所有有效的 tab 路由）
 * 提升性能和 SEO
 */
export function generateStaticParams() {
  return VALID_TABS.map((tab) => ({
    tab,
  }));
}

/**
 * 生成动态 metadata
 */
export async function generateMetadata({ params }: PageProps) {
  const { tab } = await params;
  const validTab = tab as ValidTab;

  const t = await getTranslations('metadata');

  // 验证 tab 是否有效
  if (!VALID_TABS.includes(validTab)) {
    return {
      title: t('notFoundTitle'),
    };
  }

  return {
    title: `${t(`settingsTabs.${validTab}.title`)} - ${t('settingsSuffix')}`,
    description: t(`settingsTabs.${validTab}.description`),
  };
}

/**
 * 动态路由页面：/settings/[tab]
 * 支持的路由：
 * - /settings/account
 * - /settings/agents
 * - /settings/skills
 * - /settings/mcp
 * 等等
 */
async function Page({ params }: PageProps) {
  const { tab } = await params;

  // 如果是已废弃的旧路由，直接执行服务端 308/307 永久重定向，不让其在客户端二次装载闪烁！
  if (tab && DEPRECATED_TAB_MAP[tab]) {
    const mapping = DEPRECATED_TAB_MAP[tab];
    redirect(`/settings/${mapping.parent}${mapping.sub ? `?sub=${mapping.sub}` : ''}`);
  }

  // 验证 tab 是否有效，无效则返回 404
  if (!VALID_TABS.includes(tab as ValidTab)) {
    notFound();
  }

  return (
    <Suspense fallback={<SettingsLoading />}>
      <SettingsLayout />
    </Suspense>
  );
}

export default Page;
