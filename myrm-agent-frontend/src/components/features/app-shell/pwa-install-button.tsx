'use client';

import { Download } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { usePWAInstall } from '@/hooks/usePWAInstall';
import { Button } from '@/components/primitives/button';

/**
 * [POS] PWA Install Prompt Button
 * Renders a button to install the app as a PWA if the browser supports it and it's not already installed.
 */
export function PWAInstallButton({
  variant = 'outline',
  className,
}: {
  variant?: 'default' | 'outline' | 'ghost';
  className?: string;
}) {
  const t = useTranslations('appUpdate');
  const { isInstallable, promptInstall } = usePWAInstall();

  if (!isInstallable) {
    return null;
  }

  return (
    <Button variant={variant} size="sm" onClick={promptInstall} className={className} title={t('pwaInstallTitle')}>
      <Download className="h-4 w-4 mr-2" />
      <span>{t('pwaInstallApp')}</span>
    </Button>
  );
}
