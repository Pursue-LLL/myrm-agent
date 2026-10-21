'use client';

import { useTranslations } from 'next-intl';
import { RefreshCw, Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';

export interface PollDraft {
  url: string;
  json_path: string;
  interval_seconds: number;
}

interface PollTriggerSectionProps {
  drafts: PollDraft[];
  onChange: (drafts: PollDraft[]) => void;
}

export function PollTriggerSection({ drafts, onChange }: PollTriggerSectionProps) {
  const t = useTranslations('cron');

  const updateDraft = (index: number, patch: Partial<PollDraft>) => {
    const next = [...drafts];
    next[index] = { ...next[index], ...patch };
    onChange(next);
  };

  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <RefreshCw className="h-3 w-3" />
        {t('triggerPollLabel', { defaultMessage: 'Poll (HTTP)' })}
      </div>
      <p className="text-[10px] text-muted-foreground">
        {t('triggerPollDesc', {
          defaultMessage: 'Periodically fetch a URL and fire when content changes.',
        })}
      </p>
      {drafts.map((draft, i) => (
        <div key={i} className="flex items-center gap-1.5">
          <Input
            value={draft.url}
            onChange={(e) => updateDraft(i, { url: e.target.value })}
            placeholder="https://api.example.com/data"
            className="h-7 text-xs font-mono flex-1"
          />
          <Input
            value={draft.json_path}
            onChange={(e) => updateDraft(i, { json_path: e.target.value })}
            placeholder={t('triggerPollJsonPath', { defaultMessage: 'JSONPath (optional)' })}
            className="h-7 text-xs font-mono w-36"
          />
          <Input
            type="number"
            value={draft.interval_seconds || ''}
            onChange={(e) => updateDraft(i, { interval_seconds: Number(e.target.value) || 300 })}
            placeholder="300"
            className="h-7 text-xs w-16"
            min={60}
          />
          <span className="text-[10px] text-muted-foreground">s</span>
          <button
            onClick={() => onChange(drafts.filter((_, j) => j !== i))}
            className="text-muted-foreground hover:text-destructive"
          >
            <Trash2 className="h-3 w-3" />
          </button>
        </div>
      ))}
      <Button
        variant="outline"
        size="sm"
        className="h-6 text-[10px] gap-1"
        onClick={() => onChange([...drafts, { url: '', json_path: '', interval_seconds: 300 }])}
      >
        <Plus className="h-3 w-3" /> {t('triggerPollAdd', { defaultMessage: 'Add Poll' })}
      </Button>
    </div>
  );
}
