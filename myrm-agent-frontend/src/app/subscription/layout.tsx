import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import { getTranslations } from 'next-intl/server';

interface SubscriptionLayoutProps {
  children: ReactNode;
}

export async function generateMetadata(props: { params: Promise<{ locale: string }> }): Promise<Metadata> {
  const { locale } = await props.params;
  const t = await getTranslations({ locale, namespace: 'metadata' });

  return {
    title: t('subscriptionPageTitle'),
    description: t('subscriptionPageDescription'),
  };
}

export default function SubscriptionLayout({ children }: SubscriptionLayoutProps) {
  return children;
}
