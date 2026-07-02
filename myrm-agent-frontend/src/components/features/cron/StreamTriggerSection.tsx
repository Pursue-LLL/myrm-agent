'use client';

import { useTranslations } from 'next-intl';
import { Radio, Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/primitives/select';

export interface StreamDraft {
  url: string;
  protocol: 'ws' | 'sse';
  filter_json_path: string;
  filter_regex: string;
}

interface StreamTriggerSectionProps {
  drafts: StreamDraft[];
  onChange: (drafts: StreamDraft[]) => void;
}

export function StreamTriggerSection({ drafts, onChange }: StreamTriggerSectionProps) {
  const t = useTranslations('cron');

  const updateDraft = (index: number, patch: Partial<StreamDraft>) => {
    const next = [...drafts];
    next[index] = { ...next[index], ...patch };
    onChange(next);
  };

  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <Radio className="h-3 w-3" />
        {t('triggerStreamLabel', { defaultMessage: 'Stream (WS/SSE)' })}
      </div>
      <p className="text-[10px] text-muted-foreground">
        {t('triggerStreamDesc', {
          defaultMessage: 'Real-time monitoring via outbound WebSocket or SSE connection. Works behind NAT.',
        })}
      </p>
      {drafts.map((draft, i) => (
        <div key={i} className="space-y-1">
          <div className="flex items-center gap-1.5">
            <Input
              value={draft.url}
              onChange={(e) => updateDraft(i, { url: e.target.value })}
              placeholder="wss://stream.example.com/ws"
              className="h-7 text-xs font-mono flex-1"
            />
            <Select
              value={draft.protocol}
              onValueChange={(val) => updateDraft(i, { protocol: val as 'ws' | 'sse' })}
            >
              <SelectTrigger className="h-7 w-[100px] text-xs rounded-md">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="rounded-md">
                <SelectItem value="ws">WebSocket</SelectItem>
                <SelectItem value="sse">SSE</SelectItem>
              </SelectContent>
            </Select>
            <button
              onClick={() => onChange(drafts.filter((_, j) => j !== i))}
              className="text-muted-foreground hover:text-destructive"
            >
              <Trash2 className="h-3 w-3" />
            </button>
          </div>
          <div className="flex items-center gap-1.5">
            <Input
              value={draft.filter_json_path}
              onChange={(e) => updateDraft(i, { filter_json_path: e.target.value })}
              placeholder={t('triggerStreamJsonPath', { defaultMessage: 'JSONPath e.g. $.data.price' })}
              className="h-7 text-xs font-mono flex-1"
            />
            <Input
              value={draft.filter_regex}
              onChange={(e) => updateDraft(i, { filter_regex: e.target.value })}
              placeholder={t('triggerStreamRegex', { defaultMessage: 'Regex filter (optional)' })}
              className="h-7 text-xs font-mono flex-1"
            />
          </div>
        </div>
      ))}
      <Button
        variant="outline"
        size="sm"
        className="h-6 text-[10px] gap-1"
        onClick={() =>
          onChange([...drafts, { url: '', protocol: 'ws', filter_json_path: '', filter_regex: '' }])
        }
      >
        <Plus className="h-3 w-3" /> {t('triggerStreamAdd', { defaultMessage: 'Add Stream' })}
      </Button>
    </div>
  );
}
