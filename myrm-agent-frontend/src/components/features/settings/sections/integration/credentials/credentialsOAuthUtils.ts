import type { OauthCredentialRecord, OauthIntegration } from './credentialsConstants';

export type OauthCardState = 'connected' | 'expiring' | 'expired' | 'missing';

export function resolveOauthCardState(active: OauthCredentialRecord | undefined): {
  state: OauthCardState;
  daysLeft: number;
} {
  if (!active?.connected) {
    return { state: 'missing', daysLeft: 0 };
  }
  // A refresh token the provider rejected ends the connection whatever the access token's expiry says.
  if (active.needs_reauth) {
    return { state: 'expired', daysLeft: 0 };
  }
  // A renewable credential replaces its own access token, so that token's expiry says nothing about the connection.
  if (active.renewable || !active.expires_at) {
    return { state: 'connected', daysLeft: 0 };
  }

  const nowSec = Date.now() / 1000;
  if (active.expires_at < nowSec) {
    return { state: 'expired', daysLeft: 0 };
  }
  if (active.expires_at < nowSec + 7 * 86400) {
    return { state: 'expiring', daysLeft: Math.max(1, Math.ceil((active.expires_at - nowSec) / 86400)) };
  }
  return { state: 'connected', daysLeft: 0 };
}

export function getOauthBadgeStyles(state: OauthCardState): {
  badgeColorClass: string;
  badgePulseDotClass: string;
} {
  if (state === 'connected') {
    return {
      badgeColorClass: 'bg-emerald-500/15 text-emerald-500 hover:bg-emerald-500/20 border border-emerald-500/30',
      badgePulseDotClass: 'bg-emerald-500',
    };
  }
  if (state === 'expiring') {
    return {
      badgeColorClass:
        'bg-amber-500/15 text-amber-600 dark:text-amber-400 hover:bg-amber-500/20 border border-amber-500/30',
      badgePulseDotClass: 'bg-amber-500',
    };
  }
  if (state === 'expired') {
    return {
      badgeColorClass: 'bg-red-500/15 text-red-500 hover:bg-red-500/20 border border-red-500/30',
      badgePulseDotClass: 'bg-red-500',
    };
  }
  return {
    badgeColorClass: 'bg-muted text-muted-foreground',
    badgePulseDotClass: '',
  };
}

export function getPlatformDescription(plat: OauthIntegration, locale: string): string {
  return locale === 'zh' ? plat.descZh : plat.desc;
}
