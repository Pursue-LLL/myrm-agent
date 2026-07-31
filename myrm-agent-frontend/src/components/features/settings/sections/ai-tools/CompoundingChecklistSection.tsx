'use client';

import { memo, useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { ArrowUpRight, CheckCircle2, Circle, Loader2, RefreshCw } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import SkillsLearnPanel from '@/components/features/skills/SkillsLearnPanel';
import {
  fetchCompoundingPlaybookStatus,
  type CompoundingChecklistItem,
  type CompoundingPlaybookStatus,
} from '@/services/compoundingPlaybook';
import { cn } from '@/lib/utils/classnameUtils';

interface CompoundingChecklistSectionProps {
  className?: string;
}

function ChecklistRow({
  item,
  onNavigate,
}: {
  item: CompoundingChecklistItem;
  onNavigate: (path: string) => void;
}) {
  const t = useTranslations('settings.skills.compounding');

  return (
    <div
      className={cn(
        'flex flex-col sm:flex-row sm:items-center gap-3 rounded-xl border border-border/50 bg-card/60 px-4 py-3',
        item.ready && 'border-primary/20 bg-primary/[0.03]',
      )}
    >
      <div className="flex items-start gap-3 min-w-0 flex-1">
        {item.ready ? (
          <CheckCircle2 className="h-5 w-5 text-primary shrink-0 mt-0.5" />
        ) : (
          <Circle className="h-5 w-5 text-muted-foreground/40 shrink-0 mt-0.5" />
        )}
        <div className="min-w-0">
          <p className="text-sm font-medium text-foreground">{t(`items.${item.id}.title`)}</p>
          <p className="text-xs text-muted-foreground mt-0.5">{t(`items.${item.id}.description`)}</p>
          <p className="text-[11px] text-muted-foreground/70 mt-1">
            {t('countLabel', { count: item.count })}
          </p>
        </div>
      </div>
      <Button
        variant="outline"
        size="sm"
        className="h-8 text-xs gap-1 shrink-0 self-start sm:self-center"
        onClick={() => onNavigate(item.deep_link)}
      >
        {t('open')}
        <ArrowUpRight className="h-3 w-3" />
      </Button>
    </div>
  );
}

const CompoundingChecklistSection = memo(({ className }: CompoundingChecklistSectionProps) => {
  const t = useTranslations('settings.skills.compounding');
  const router = useRouter();
  const [status, setStatus] = useState<CompoundingPlaybookStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const next = await fetchCompoundingPlaybookStatus();
      setStatus(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleNavigate = useCallback(
    (path: string) => {
      router.push(path);
    },
    [router],
  );

  return (
    <div className={cn('space-y-6', className)}>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-foreground">{t('title')}</h2>
          <p className="text-sm text-muted-foreground mt-1">{t('subtitle')}</p>
        </div>
        <Button variant="ghost" size="sm" className="h-8 text-xs gap-1 self-start" onClick={() => void load()} disabled={loading}>
          {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
          {t('refresh')}
        </Button>
      </div>

      {loading && !status ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-8 justify-center">
          <Loader2 className="h-4 w-4 animate-spin" />
          {t('loading')}
        </div>
      ) : null}

      {error ? <p className="text-sm text-destructive">{error}</p> : null}

      {status ? (
        <>
          <div className="rounded-xl border border-border/40 bg-muted/20 px-4 py-3 text-sm">
            <span className="font-medium text-foreground">{t('progress')}</span>
            <span className="text-muted-foreground ml-2">
              {t('progressValue', { ready: status.ready_count, total: status.total_count })}
            </span>
          </div>

          <div className="space-y-3">
            {status.items.map((item) => (
              <ChecklistRow key={item.id} item={item} onNavigate={handleNavigate} />
            ))}
          </div>
        </>
      ) : null}

      <div className="pt-2 border-t border-border/40">
        <p className="text-xs text-muted-foreground mb-3">{t('learnHint')}</p>
        <SkillsLearnPanel />
      </div>
    </div>
  );
});

CompoundingChecklistSection.displayName = 'CompoundingChecklistSection';

export default CompoundingChecklistSection;
