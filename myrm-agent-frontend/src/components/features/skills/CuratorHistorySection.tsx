'use client';

import { memo } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { ChevronDown, ChevronRight, History, Loader2 } from 'lucide-react';
import { Badge } from '@/components/primitives/badge';
import { formatRelativeTime } from '@/lib/utils/relativeTime';
import type { CuratorHistoryEntry, CuratorTransitionReason } from '@/services/skill';

/** Three of the five reason codes mean "went unused past a threshold", so users get three phrases. */
const REASON_KEYS = {
  inactive: 'historyReason.inactive',
  stale: 'historyReason.inactive',
  archive: 'historyReason.inactive',
  low_quality: 'historyReason.lowQuality',
  lru_eviction: 'historyReason.overLimit',
} as const satisfies Record<CuratorTransitionReason, string>;

interface CuratorHistorySectionProps {
  open: boolean;
  loading: boolean;
  entries: CuratorHistoryEntry[];
  onToggle: () => void;
}

const CuratorHistorySection = memo(({ open, loading, entries, onToggle }: CuratorHistorySectionProps) => {
  const t = useTranslations('settings.skills.curator');
  const tCard = useTranslations('settings.skills.card');
  const locale = useLocale();

  return (
    <div className="pt-3 border-t" data-testid="curator-history">
      <button
        type="button"
        data-testid="curator-history-toggle"
        onClick={onToggle}
        className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
      >
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        <History size={12} />
        {t('recentRuns')}
      </button>

      {open && (
        <div className="mt-2 space-y-2">
          {loading ? (
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground py-2">
              <Loader2 size={12} className="animate-spin" />
              {t('loadingHistory')}
            </div>
          ) : entries.length === 0 ? (
            <p className="text-xs text-muted-foreground py-2">{t('noHistory')}</p>
          ) : (
            entries.map((entry, idx) => (
              <div
                key={`${entry.timestamp}-${idx}`}
                data-testid="curator-history-entry"
                className="rounded-lg border px-3 py-2 text-xs space-y-1"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-muted-foreground">{formatRelativeTime(entry.timestamp, locale)}</span>
                    <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                      {entry.trigger === 'manual' ? t('triggerManual') : t('triggerBackground')}
                    </Badge>
                  </div>
                  <span className="text-muted-foreground">{entry.duration_ms}ms</span>
                </div>
                <div className="flex items-center gap-3 text-muted-foreground">
                  <span>{t('historyScanned', { count: entry.skills_scanned })}</span>
                  {entry.stale_count > 0 && (
                    <span className="text-yellow-700 dark:text-yellow-500">
                      {tCard('stale')} {entry.stale_count}
                    </span>
                  )}
                  {entry.archived_count > 0 && (
                    <span className="text-red-600 dark:text-red-400">
                      {tCard('archived')} {entry.archived_count}
                    </span>
                  )}
                  {entry.total_transitions === 0 && (
                    <span className="text-green-700 dark:text-green-400">{t('noChanges')}</span>
                  )}
                </div>
                {entry.transitions.length > 0 && (
                  <div className="pt-1 space-y-0.5">
                    {entry.transitions.map((tr) => (
                      <div
                        key={tr.skill_name}
                        className="text-[11px] text-muted-foreground pl-2 border-l-2 border-muted"
                      >
                        <span className="font-medium text-foreground">{tr.skill_name}</span> → {tCard(tr.to_status)}
                        <span className="ml-1 opacity-70">({t(REASON_KEYS[tr.reason])})</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
});

CuratorHistorySection.displayName = 'CuratorHistorySection';

export default CuratorHistorySection;
