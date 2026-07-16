import type { OauthCredentialRecord, OauthIntegration } from './credentialsConstants';

export type OauthCardState = 'connected' | 'expiring' | 'expired' | 'missing';

export function resolveOauthCardState(active: OauthCredentialRecord | undefined): {
  state: OauthCardState;
  daysLeft: number;
} {
  let state: OauthCardState = 'missing';
  let daysLeft = 0;

  if (active) {
    if (active.connected) {
      if (active.expires_at) {
        const nowSec = Date.now() / 1000;
        if (active.expires_at < nowSec) {
          state = 'expired';
        } else if (active.expires_at < nowSec + 7 * 86400) {
          state = 'expiring';
          daysLeft = Math.max(1, Math.ceil((active.expires_at - nowSec) / 86400));
        } else {
          state = 'connected';
        }
      } else {
        state = 'connected';
      }
    } else {
      state = 'missing';
    }
  }

  return { state, daysLeft };
}

export function getOauthBadgeStyles(state: OauthCardState): {
  badgeColorClass: string;
  badgePulseDotClass: string;
} {
  if (state === 'connected') {
    return {
      badgeColorClass:
        'bg-emerald-500/15 text-emerald-500 hover:bg-emerald-500/20 border border-emerald-500/30',
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
