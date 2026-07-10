import { Metadata } from 'next';
import { getTranslations } from 'next-intl/server';
import ProjectsDashboard from '@/components/features/projects/ProjectsDashboard';

export async function generateMetadata(props: { params: Promise<{ locale: string }> }): Promise<Metadata> {
  const params = await props.params;
  const t = await getTranslations({ locale: params.locale, namespace: 'projects' });
  return { title: t('title') };
}

export default function ProjectsPage() {
  return <ProjectsDashboard />;
}
