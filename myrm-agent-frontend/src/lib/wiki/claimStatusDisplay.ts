/**
 * [OUTPUT]
 * WikiClaimStatus, claimStatusClass, claimStatusLabel, shouldShowClaimStatusBadge.
 *
 * [POS]
 * Wiki claim 状态展示纯函数。供 Chat SourceChunkDrawer 与 Settings 概念详情面板共享 badge 样式与降噪规则。
 */

export type WikiClaimStatus = 'supported' | 'contested' | 'unsupported' | 'unknown';

export type WikiClaimStatusLabels = Record<WikiClaimStatus, string>;

export function claimStatusClass(status: string): string {
  switch (status) {
    case 'supported':
      return 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/20';
    case 'contested':
      return 'bg-amber-500/10 text-amber-800 dark:text-amber-200 border-amber-500/20';
    case 'unsupported':
      return 'bg-red-500/10 text-red-700 dark:text-red-300 border-red-500/20';
    default:
      return 'bg-muted/40 text-muted-foreground border-border/60';
  }
}

export function claimStatusLabel(status: string, labels: WikiClaimStatusLabels): string {
  switch (status) {
    case 'supported':
      return labels.supported;
    case 'contested':
      return labels.contested;
    case 'unsupported':
      return labels.unsupported;
    default:
      return labels.unknown;
  }
}

/** Drawer surfaces only surface contested/unsupported to avoid badge noise. */
export function shouldShowClaimStatusBadge(status?: string): status is 'contested' | 'unsupported' {
  return status === 'contested' || status === 'unsupported';
}

/** Show compile confidence when explicitly set (not unknown fallback 0.5). */
export function shouldShowClaimConfidence(confidence?: number): boolean {
  if (confidence === undefined || confidence === null) {
    return false;
  }
  if (confidence <= 0) {
    return false;
  }
  return confidence !== 0.5;
}

export function formatClaimConfidence(confidence: number, locale: string = 'en'): string {
  return new Intl.NumberFormat(locale, { style: 'percent', maximumFractionDigits: 0 }).format(confidence);
}
