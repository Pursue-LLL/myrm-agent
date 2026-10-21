import WorkspaceLayout from '@/components/features/workspace/WorkspaceLayout';
import { Metadata } from 'next';
import { getTranslations } from 'next-intl/server';

export async function generateMetadata(props: { params: Promise<{ locale: string }> }): Promise<Metadata> {
  const params = await props.params;
  const t = await getTranslations({ locale: params.locale, namespace: 'multiPane' });
  return { title: t('title') };
}

export default function WorkPage() {
  return <WorkspaceLayout />;
}
