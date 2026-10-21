import { Suspense } from 'react';
import { notFound, redirect } from 'next/navigation';
import SettingsLayout from '@/components/features/settings/SettingsLayout';
import { getSettingsTabRedirectPath, isSettingsTab } from '@/components/features/settings/settingsRoutes';
import RouteSegmentLoading from '@/components/layout/RouteSegmentLoading';
import { getTranslations } from 'next-intl/server';
import { defaultLocale } from '@/i18n/config';

interface PageProps {
  params: Promise<{
    tab: string;
  }>;
}

export async function generateMetadata({ params }: PageProps) {
  const { tab } = await params;
  const t = await getTranslations({ locale: defaultLocale, namespace: 'metadata' });

  if (!isSettingsTab(tab)) {
    return {
      title: t('notFoundTitle'),
    };
  }

  return {
    title: `${t(`settingsTabs.${tab}.title`)} - ${t('settingsSuffix')}`,
    description: t(`settingsTabs.${tab}.description`),
  };
}

async function SettingsTabPage({ params }: PageProps) {
  const { tab } = await params;

  const redirectPath = getSettingsTabRedirectPath(tab);
  if (redirectPath) {
    redirect(redirectPath);
  }

  if (!isSettingsTab(tab)) {
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
