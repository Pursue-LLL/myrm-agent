'use client';

/**
 * [INPUT]
 * @/services/cron::{updateCronJob, CronJob} (POS: Frontend Cron API client)
 *
 * [OUTPUT]
 * AcceptanceCriteriaEditor: per-job acceptance criteria PATCH editor for Settings detail.
 *
 * [POS]
 * Cron job detail editor. Enables compounding verify checklist completion on existing jobs.
 */

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Plus, ShieldCheck, Trash2 } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { toast } from 'sonner';
import type { CronJob } from '@/services/cron';
import { updateCronJob } from '@/services/cron';

interface CriterionRow {
  type: string;
  description: string;
}

interface AcceptanceCriteriaEditorProps {
  job: CronJob;
  onUpdated: () => void;
}

function parseCriteria(raw: CronJob['acceptance_criteria']): CriterionRow[] {
  if (!raw?.length) {
    return [];
  }
  return raw.map((entry) => ({
    type: typeof entry.type === 'string' ? entry.type : 'semantic',
    description:
      typeof entry.description === 'string'
        ? entry.description
        : typeof entry.command === 'string'
          ? entry.command
          : '',
  }));
}

export function AcceptanceCriteriaEditor({ job, onUpdated }: AcceptanceCriteriaEditorProps) {
  const t = useTranslations('cron');
  const [criteria, setCriteria] = useState<CriterionRow[]>(() => parseCriteria(job.acceptance_criteria));
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setCriteria(parseCriteria(job.acceptance_criteria));
  }, [job.acceptance_criteria, job.id]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const valid = criteria.filter((row) => row.description.trim());
      await updateCronJob(job.id, {
        acceptance_criteria:
          valid.length > 0
            ? valid.map((row) => ({
                type: row.type,
                description: row.description.trim(),
              }))
            : null,
      });
      onUpdated();
      toast.success(t('acceptanceCriteriaUpdated'));
    } catch {
      toast.error(t('actionFail'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-lg border bg-card px-3 py-2.5 space-y-2">
      <div className="flex items-center gap-1.5">
        <ShieldCheck className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="text-xs font-medium text-muted-foreground">{t('acceptanceCriteria')}</span>
      </div>
      <p className="text-[11px] text-muted-foreground">{t('acceptanceCriteriaHint')}</p>
      {criteria.map((criterion, idx) => (
        <div key={idx} className="flex items-start gap-1.5">
          <Select
            value={criterion.type}
            onValueChange={(value) => {
              const next = [...criteria];
              next[idx] = { ...next[idx], type: value };
              setCriteria(next);
            }}
          >
            <SelectTrigger className="h-7 text-xs w-24 shrink-0">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="semantic">{t('criterionSemantic')}</SelectItem>
              <SelectItem value="shell">{t('criterionShell')}</SelectItem>
            </SelectContent>
          </Select>
          <Input
            placeholder={
              criterion.type === 'shell' ? t('criterionShellPlaceholder') : t('criterionSemanticPlaceholder')
            }
            value={criterion.description}
            onChange={(e) => {
              const next = [...criteria];
              next[idx] = { ...next[idx], description: e.target.value };
              setCriteria(next);
            }}
            className="h-7 text-xs flex-1"
          />
          <button
            type="button"
            onClick={() => setCriteria(criteria.filter((_, i) => i !== idx))}
            className="h-7 w-7 flex items-center justify-center text-muted-foreground hover:text-destructive shrink-0"
          >
            <Trash2 className="h-3 w-3" />
          </button>
        </div>
      ))}
      {criteria.length < 10 && (
        <button
          type="button"
          onClick={() => setCriteria([...criteria, { type: 'semantic', description: '' }])}
          className="text-[11px] text-muted-foreground hover:text-primary flex items-center gap-1"
        >
          <Plus className="h-3 w-3" />
          {t('addCriterion')}
        </button>
      )}
      <div className="flex justify-end pt-1">
        <Button size="sm" className="h-7 text-xs" onClick={() => void handleSave()} disabled={saving}>
          {t('save')}
        </Button>
      </div>
    </div>
  );
}
