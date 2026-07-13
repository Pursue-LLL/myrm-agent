import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import { getTranslations } from 'next-intl/server';

interface LibraryLayoutProps {
  children: ReactNode;
}

export async function generateMetadata(props: { params: Promise<{ locale: string }> }): Promise<Metadata> {
  const { locale } = await props.params;
  const t = await getTranslations({ locale, namespace: 'metadata' });

  return {
    title: t('libraryPageTitle'),
    description: t('libraryPageDescription'),
  };
}

export default function LibraryLayout({ children }: LibraryLayoutProps) {
  return children;
}
