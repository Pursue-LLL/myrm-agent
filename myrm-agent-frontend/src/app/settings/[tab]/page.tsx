import { Suspense } from 'react';
import { notFound, redirect } from 'next/navigation';
import SettingsLayout from '@/components/features/settings/SettingsLayout';
import RouteSegmentLoading from '@/components/layout/RouteSegmentLoading';
import { getTranslations } from 'next-intl/server';
import { defaultLocale } from '@/i18n/config';

const VALID_TABS = [
  'account',
  'preferences',
  'personalization',
  'agents',
  'security',
  'riskRules',
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
  'eval',
  'credentials',
  'wiki',
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
  'enterprise',
  'system',
  'about',
] as const;

const DEPRECATED_TAB_MAP: Record<string, { parent: string; sub?: string }> = {
  persona: { parent: 'personalization' },
  toolCapabilities: { parent: 'models' },
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
  eval: { parent: 'developer' },
  about: { parent: 'system', sub: 'about' },
};

type ValidTab = (typeof VALID_TABS)[number];

interface PageProps {
  params: Promise<{
    tab: string;
  }>;
}

export async function generateMetadata({ params }: PageProps) {
  const { tab } = await params;
  const validTab = tab as ValidTab;
  const t = await getTranslations({ locale: defaultLocale, namespace: 'metadata' });

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

export const prefetch = 'allow-runtime';

async function SettingsTabPage({ params }: PageProps) {
  const { tab } = await params;

  if (tab && DEPRECATED_TAB_MAP[tab]) {
    const mapping = DEPRECATED_TAB_MAP[tab];
    redirect(`/settings/${mapping.parent}${mapping.sub ? `?sub=${mapping.sub}` : ''}`);
  }

  if (!VALID_TABS.includes(tab as ValidTab)) {
    notFound();
  }

  return <SettingsLayout />;
}

export default function Page(props: PageProps) {
  return (
    <Suspense fallback={<RouteSegmentLoading variant="settings" />}>
      <SettingsTabPage params={props.params} />
    </Suspense>
  );
}
