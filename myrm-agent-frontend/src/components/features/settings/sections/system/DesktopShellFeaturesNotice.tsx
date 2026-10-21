'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { AppWindow, Shield } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { isTauriRuntime } from '@/lib/deploy-mode';

/**
 * Explains that Locked Use, Privacy Curtain, and OS approval highlights require the desktop shell.
 * Browser-only WebUI still supports in-app desktop automation approvals without OS overlays.
 */
const DesktopShellFeaturesNotice = memo(() => {
  const t = useTranslations('settings.desktopShellFeatures');

  if (isTauriRuntime()) {
    return null;
  }

  return (
    <section className="space-y-4">
      <div className="flex items-center gap-3 px-2">
        <AppWindow className="w-5 h-5 text-muted-foreground shrink-0" />
        <h2 className="text-sm font-black uppercase tracking-[0.2em] text-muted-foreground/70">{t('title')}</h2>
      </div>

      <div
        className={cn(
          'rounded-2xl border border-border/40 bg-card/50 backdrop-blur-sm p-5',
          'flex flex-col gap-3 sm:flex-row sm:items-start sm:gap-4',
        )}
      >
        <div className="p-2 rounded-lg bg-indigo-500/10 shrink-0">
          <Shield className="w-4 h-4 text-indigo-500" />
        </div>
        <div className="min-w-0 space-y-2">
          <p className="text-sm font-semibold text-foreground">{t('headline')}</p>
          <p className="text-xs text-muted-foreground leading-relaxed">{t('body')}</p>
          <ul className="text-xs text-muted-foreground leading-relaxed list-disc pl-4 space-y-1">
            <li>{t('bulletLockedUse')}</li>
            <li>{t('bulletCurtain')}</li>
            <li>{t('bulletOsHighlight')}</li>
          </ul>
        </div>
      </div>
    </section>
  );
});

DesktopShellFeaturesNotice.displayName = 'DesktopShellFeaturesNotice';

export default DesktopShellFeaturesNotice;
