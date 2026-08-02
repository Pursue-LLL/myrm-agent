'use client';

import { useTranslations } from 'next-intl';
import OAuthButtons from '@/components/auth/OAuthButtons';
import type { ThemeMarketplaceGateState } from '@/lib/theme-marketplace-gate';

interface ThemeMarketplaceGateBannerProps {
  gate: Exclude<ThemeMarketplaceGateState, 'loading' | 'ready'>;
  redirectPath?: string;
}

const ThemeMarketplaceGateBanner = ({
  gate,
  redirectPath = '/settings/theme-studio',
}: ThemeMarketplaceGateBannerProps) => {
  const t = useTranslations('settings.themeStudio.marketplaceGate');

  if (gate === 'needs_auth') {
    return (
      <div className="rounded-xl border border-border/60 bg-muted/10 p-4 space-y-3">
        <div className="space-y-1">
          <h3 className="text-sm font-semibold text-foreground">{t('needsAuthTitle')}</h3>
          <p className="text-xs text-muted-foreground">{t('needsAuthBody')}</p>
        </div>
        <OAuthButtons redirectPath={redirectPath} />
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-border/60 bg-muted/10 p-4 space-y-1">
      <h3 className="text-sm font-semibold text-foreground">{t('offlineTitle')}</h3>
      <p className="text-xs text-muted-foreground">{t('offlineBody')}</p>
    </div>
  );
};

export default ThemeMarketplaceGateBanner;
