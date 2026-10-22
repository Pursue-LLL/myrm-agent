'use client';

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Loader2, RotateCcw } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { toast } from '@/hooks/shared/useToast';
import {
  listSkillPackageRevisions,
  restoreSkillPackageRevision,
  type SkillPackageRevisionSummary,
} from '@/services/skill/optimization';

interface SkillPackageRevisionsPanelProps {
  skillId: string;
  onRestored?: () => void;
  className?: string;
}

export function SkillPackageRevisionsPanel({ skillId, onRestored, className }: SkillPackageRevisionsPanelProps) {
  const t = useTranslations('settings.skills.detail.history');
  const [rows, setRows] = useState<SkillPackageRevisionSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [restoring, setRestoring] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await listSkillPackageRevisions(skillId);
      setRows(res.revisions);
    } catch {
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [skillId]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleRestore = async (revisionNumber: number) => {
    setRestoring(revisionNumber);
    try {
      await restoreSkillPackageRevision(skillId, revisionNumber);
      toast({ title: t('packageRestoreSuccess') });
      onRestored?.();
      await load();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      toast({ variant: 'destructive', title: t('packageRestoreFailed'), description: msg });
    } finally {
      setRestoring(null);
    }
  };

  if (loading) {
    return (
      <div className={className}>
        <Loader2 className="size-4 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (rows.length === 0) {
    return <p className={`text-sm text-muted-foreground ${className ?? ''}`}>{t('packageEmpty')}</p>;
  }

  return (
    <ul className={`space-y-2 ${className ?? ''}`}>
      {rows.map((row) => (
        <li
          key={row.revision_id}
          className="flex flex-col gap-2 rounded-lg border border-border/60 p-3 sm:flex-row sm:items-center sm:justify-between"
        >
          <div className="min-w-0">
            <p className="text-sm font-medium">{t('packageRevisionLabel', { n: row.revision_number })}</p>
            <p className="text-xs text-muted-foreground truncate">{row.resource_paths.join(', ') || t('packageSkillOnly')}</p>
          </div>
          <Button
            size="sm"
            variant="outline"
            className="shrink-0 gap-1.5"
            disabled={restoring === row.revision_number}
            onClick={() => void handleRestore(row.revision_number)}
          >
            {restoring === row.revision_number ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <RotateCcw className="size-3.5" />
            )}
            {t('packageRestore')}
          </Button>
        </li>
      ))}
    </ul>
  );
}
