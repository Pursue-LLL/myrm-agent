'use client';

import { useLocale, useTranslations } from 'next-intl';
import { IconAlertCircle } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { cn } from '@/lib/utils';
import { SUPPORTED_INTEGRATIONS } from './credentialsConstants';
import {
  getOauthBadgeStyles,
  getPlatformDescription,
  resolveOauthCardState,
} from './credentialsOAuthUtils';
import type { CredentialsSectionState } from './useCredentialsSection';

type CredentialsOAuthPanelProps = Pick<
  CredentialsSectionState,
  | 'googleOauthPolling'
  | 'googleWorkspaceWriteEnabled'
  | 'handleGoogleWorkspaceConnect'
  | 'isOauthLoading'
  | 'oauthCreds'
  | 'openConnectModal'
  | 'prepareDisconnect'
>;

export function CredentialsOAuthPanel({
  googleOauthPolling,
  googleWorkspaceWriteEnabled,
  handleGoogleWorkspaceConnect,
  isOauthLoading,
  oauthCreds,
  openConnectModal,
  prepareDisconnect,
}: CredentialsOAuthPanelProps) {
  const t = useTranslations('settings.credentials');
  const locale = useLocale();

  return (
    <div className="mt-8 pt-8 border-t border-border">
      <h3 className="text-lg font-semibold flex items-center gap-2 text-foreground">{t('oauthTitle')}</h3>
      <p className="text-sm text-muted-foreground mt-1 mb-6 leading-relaxed">{t('oauthDescription')}</p>

      {isOauthLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="h-32 rounded-xl bg-muted animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {SUPPORTED_INTEGRATIONS.map((plat) => {
            const active = oauthCreds.find((cred) => cred.issuer === plat.id);
            const desc = getPlatformDescription(plat, locale);
            const { state, daysLeft } = resolveOauthCardState(active);
            const { badgeColorClass, badgePulseDotClass } = getOauthBadgeStyles(state);

            let badgeText = t('disconnected');
            if (state === 'connected') badgeText = t('connected');
            else if (state === 'expiring') badgeText = t('expiringSoon', { days: daysLeft });
            else if (state === 'expired') badgeText = t('expired');

            return (
              <div
                key={plat.id}
                className={cn(
                  'flex flex-col justify-between p-5 rounded-xl border transition-all duration-200 hover:shadow-md bg-card/50',
                  state === 'connected'
                    ? 'border-emerald-500/20'
                    : state === 'expiring'
                      ? 'border-amber-500/30'
                      : state === 'expired'
                        ? 'border-red-500/30 bg-red-500/5'
                        : 'border-border',
                )}
              >
                <div>
                  <div className="flex items-center justify-between">
                    <div className="font-semibold text-base text-foreground">{plat.name}</div>
                    <Badge
                      variant={active ? 'default' : 'secondary'}
                      className={cn('px-2.5 py-0.5 rounded-full text-xs font-medium', badgeColorClass)}
                    >
                      <div className="flex items-center gap-1.5">
                        {state !== 'missing' && (
                          <span className={cn('h-1.5 w-1.5 rounded-full animate-pulse', badgePulseDotClass)} />
                        )}
                        {badgeText}
                      </div>
                    </Badge>
                  </div>
                  <p className="text-sm text-muted-foreground mt-2 line-clamp-2">{desc}</p>

                  {state === 'expired' && (
                    <div className="mt-4 flex items-center gap-2.5 p-3 rounded-lg border border-red-500/20 bg-red-500/5 text-xs text-red-600 dark:text-red-400 leading-relaxed animate-in fade-in-50 duration-200">
                      <IconAlertCircle className="w-4 h-4 flex-shrink-0 text-red-500" />
                      <div className="flex-1 font-medium">
                        {locale === 'zh'
                          ? '当前凭证已失效（可能在三方平台被吊销或到期）。请点击一键修复重新授权，以恢复该服务。'
                          : 'This authorization has invalidated (revoked or expired on the platform). Please click Fix Now to re-authorize.'}
                      </div>
                      <Button
                        size="sm"
                        variant="destructive"
                        onClick={() => void openConnectModal(plat)}
                        className="h-7 px-2.5 text-xs font-semibold whitespace-nowrap bg-red-500 hover:bg-red-600 text-white flex-shrink-0 shadow-red-500/20"
                      >
                        {locale === 'zh' ? '一键修复' : 'Fix Now'}
                      </Button>
                    </div>
                  )}

                  {plat.oauthFlow === 'google_workspace' && active && state !== 'missing' && (
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <Badge
                        variant="outline"
                        className={cn(
                          'text-xs font-medium',
                          googleWorkspaceWriteEnabled
                            ? 'border-violet-500/40 text-violet-600 dark:text-violet-300 bg-violet-500/10'
                            : 'border-border text-muted-foreground',
                        )}
                      >
                        {googleWorkspaceWriteEnabled ? t('googleOauthWriteTierOn') : t('googleOauthReadonlyTier')}
                      </Badge>
                      {!googleWorkspaceWriteEnabled && (
                        <Button
                          size="sm"
                          variant="secondary"
                          className="h-7 text-xs"
                          disabled={googleOauthPolling}
                          onClick={() => void handleGoogleWorkspaceConnect('write')}
                        >
                          {googleOauthPolling ? t('googleOauthPolling') : t('googleOauthEnableWrite')}
                        </Button>
                      )}
                    </div>
                  )}

                  {active && state !== 'expired' && (
                    <div className="mt-4 space-y-1.5 bg-muted/30 rounded-lg p-3 text-xs border border-border/50">
                      {active.user_id && (
                        <div className="flex justify-between items-center">
                          <span className="text-muted-foreground">{t('userId')}:</span>
                          <span className="font-medium font-mono text-foreground">{active.user_id}</span>
                        </div>
                      )}
                      {active.scope && (
                        <div className="flex justify-between items-center">
                          <span className="text-muted-foreground">{t('scope')}:</span>
                          <span className="font-medium max-w-[180px] truncate text-foreground">{active.scope}</span>
                        </div>
                      )}
                      <div className="flex justify-between items-center">
                        <span className="text-muted-foreground">{t('expiresAt')}:</span>
                        <span className="font-medium text-foreground">
                          {active.expires_at
                            ? new Date(active.expires_at * 1000).toLocaleString()
                            : t('neverExpires')}
                        </span>
                      </div>
                    </div>
                  )}
                </div>

                <div className="mt-5 flex justify-end">
                  {active ? (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => void prepareDisconnect(plat)}
                      className="text-red-500 border-red-500/30 hover:border-red-500 hover:bg-red-500/10"
                    >
                      {t('disconnect')}
                    </Button>
                  ) : (
                    <Button size="sm" variant="default" onClick={() => void openConnectModal(plat)}>
                      {t('connect')}
                    </Button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
