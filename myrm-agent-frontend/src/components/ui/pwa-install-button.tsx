'use client';

import { Download } from 'lucide-react';
import { usePWAInstall } from '@/hooks/usePWAInstall';
import { Button } from '@/components/ui/button';

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
  const { isInstallable, promptInstall } = usePWAInstall();

  if (!isInstallable) {
    return null;
  }

  return (
    <Button variant={variant} size="sm" onClick={promptInstall} className={className} title="安装为桌面应用">
      <Download className="h-4 w-4 mr-2" />
      <span>安装应用</span>
    </Button>
  );
}
