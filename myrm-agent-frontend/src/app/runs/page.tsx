import { getTranslations } from 'next-intl/server';
import { RunsHub } from '@/components/features/runs/RunsHub';

export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: 'runs' });
  return {
    title: `${t('title')} - MyrmAgent`,
  };
}

export default function RunsPage() {
  return <RunsHub />;
}
