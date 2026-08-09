import React from 'react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';

export interface MemoryAbHistoryItem {
  timestamp?: number;
  dataset_id?: string;
  profile_id?: string | null;
  per_profile?: Record<
    string,
    {
      pass_rate?: number;
      pass_count?: number;
      fail_count?: number;
      error_count?: number;
      memory_tool_calls?: number;
    }
  >;
}

interface Props {
  items: MemoryAbHistoryItem[];
  selectedTimestamp?: number | null;
  onSelect: (timestamp: number) => void;
}

export default function MemoryAbHistoryTable({ items, selectedTimestamp, onSelect }: Props) {
  const t = useTranslations('evalLab.memoryAb');

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
              <th className="px-4 py-2 font-medium">{t('armNoMemory')}</th>
              <th className="px-4 py-2 font-medium">{t('armWithMemory')}</th>
              <th className="px-4 py-2 font-medium" />
            </tr>
          </thead>
          <tbody className="divide-y">
            {items.map((item) => {
              const ts = item.timestamp;
              const off = item.per_profile?.memory_off;
              const on = item.per_profile?.memory_on;
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
                  </td>
                  <td className="px-4 py-2 whitespace-nowrap">
                    {off != null ? `${Math.round((off.pass_rate ?? 0) * 100)}%` : '-'}
                    {off?.memory_tool_calls != null && (
                      <span className="text-xs text-muted-foreground ml-1">({off.memory_tool_calls})</span>
                    )}
                  </td>
                  <td className="px-4 py-2 whitespace-nowrap">
                    {on != null ? `${Math.round((on.pass_rate ?? 0) * 100)}%` : '-'}
                    {on?.memory_tool_calls != null && (
                      <span className="text-xs text-muted-foreground ml-1">({on.memory_tool_calls})</span>
                    )}
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
