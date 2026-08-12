import React from 'react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';

export interface MatrixHistoryItem {
  timestamp?: number;
  dataset_id?: string;
  profile_id?: string | null;
  eval_type?: string | null;
  agent_model?: string | null;
  judge_model?: string | null;
  stable_rate?: number | null;
  limit?: number | null;
  aborted?: boolean;
}

interface Props {
  items: MatrixHistoryItem[];
  selectedTimestamp?: number | null;
  onSelect: (timestamp: number) => void;
}

export default function MatrixHistoryTable({ items, selectedTimestamp, onSelect }: Props) {
  const t = useTranslations('evalLab.matrix');

  if (items.length === 0) {
    return null;
  }

  return (
    <div className="border rounded-lg overflow-hidden">
      <div className="px-4 py-3 bg-muted/50 border-b">
        <h3 className="text-sm font-medium">{t('historyTitle')}</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm text-left min-w-[560px]">
          <thead className="bg-muted/30 border-b">
            <tr>
              <th className="px-4 py-2 font-medium">{t('historyTime')}</th>
              <th className="px-4 py-2 font-medium">{t('historyDataset')}</th>
              <th className="px-4 py-2 font-medium">{t('historyAgentModel')}</th>
              <th className="px-4 py-2 font-medium">{t('historyJudge')}</th>
              <th className="px-4 py-2 font-medium">{t('stableRate')}</th>
              <th className="px-4 py-2 font-medium" />
            </tr>
          </thead>
          <tbody className="divide-y">
            {items.map((item) => {
              const ts = item.timestamp;
              const isSelected = ts != null && ts === selectedTimestamp;
              return (
                <tr
                  key={ts ?? `run-${item.dataset_id ?? ''}`}
                  className={`bg-card hover:bg-muted/20 ${isSelected ? 'bg-primary/5' : ''}`}
                >
                  <td className="px-4 py-2 text-muted-foreground whitespace-nowrap">
                    {ts ? new Date(ts * 1000).toLocaleString() : '-'}
                  </td>
                  <td className="px-4 py-2 font-mono text-xs">
                    {item.dataset_id?.replace(/^wb-bench-/, '') ?? '-'}
                    {item.eval_type === 'layered' && (
                      <span className="ml-1.5 px-1.5 py-0.5 text-[10px] font-medium bg-primary/10 text-primary rounded">
                        {t('historyLayeredBadge')}
                      </span>
                    )}
                    {item.limit != null && (
                      <span
                        className="ml-1.5 px-1.5 py-0.5 text-[10px] font-medium bg-violet-500/10 text-violet-600 dark:text-violet-400 rounded"
                        title={t('sampledTitle')}
                      >
                        {t('sampled')} · {item.limit}
                      </span>
                    )}
                    {item.aborted && (
                      <span className="ml-1.5 px-1.5 py-0.5 text-[10px] font-medium bg-amber-500/10 text-amber-600 dark:text-amber-400 rounded">
                        {t('historyAbortedBadge')}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2 font-mono text-xs text-muted-foreground whitespace-nowrap">
                    {item.agent_model && item.agent_model !== 'unknown' ? item.agent_model : '-'}
                  </td>
                  <td className="px-4 py-2 font-mono text-xs text-muted-foreground whitespace-nowrap">
                    {item.judge_model && item.judge_model !== 'none' ? item.judge_model : '-'}
                  </td>
                  <td className="px-4 py-2 whitespace-nowrap">
                    {item.stable_rate != null ? `${Math.round(item.stable_rate * 100)}%` : '-'}
                  </td>
                  <td className="px-4 py-2 text-right">
                    <Button
                      variant={isSelected ? 'secondary' : 'ghost'}
                      size="sm"
                      onClick={() => ts != null && onSelect(ts)}
                      disabled={isSelected}
                    >
                      {isSelected ? t('historyCurrent') : t('historyView')}
                    </Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
