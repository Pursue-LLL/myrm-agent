'use client';

/**
 * [INPUT]
 * - store/offline/offlineStagingStore::StagingRecord (POS: Offline staging queue item schema)
 *
 * [OUTPUT]
 * - StagedVaultQueueView: Standalone list view rendering staged notes and their sync states.
 *
 * [POS]
 * Extracted pure presentational component for mobile offline staging queue inspection.
 */

import React from 'react';
import { Send } from 'lucide-react';
import type { StagingRecord } from '@/store/offline/offlineStagingStore';

export interface StagedVaultQueueViewProps {
  records: readonly StagingRecord[];
  titleLabel: string;
  emptyLabel: string;
  untitledLabel: string;
  convertToTaskLabel?: string;
  onConvertToTask?: (content: string) => void;
}

export const StagedVaultQueueView: React.FC<StagedVaultQueueViewProps> = ({
  records,
  titleLabel,
  emptyLabel,
  untitledLabel,
  convertToTaskLabel,
  onConvertToTask,
}) => {
  return (
    <div className="mt-3 max-h-60 overflow-y-auto space-y-2 pr-1" data-testid="staged-vault-queue-view">
      <h3 className="text-xs font-semibold text-muted-foreground mb-1">{titleLabel}</h3>
      {records.length === 0 ? (
        <p className="text-xs text-muted-foreground text-center py-4">{emptyLabel}</p>
      ) : (
        records.map((item) => {
          const displayTitle =
            item.payload.title || item.payload.content.slice(0, 24) || untitledLabel;
          const isSynced = item.status === 'synced';

          return (
            <div
              key={item.id}
              data-testid={`staging-record-${item.id}`}
              className="p-2.5 rounded-lg border border-border/40 bg-muted/20 text-xs flex flex-col gap-1"
            >
              <div className="flex items-center justify-between">
                <span className="font-medium truncate text-foreground">{displayTitle}</span>
                <span
                  className={`text-[9px] px-1.5 py-0.5 rounded-full border ${
                    isSynced
                      ? 'bg-emerald-500/10 text-emerald-600 border-emerald-500/20'
                      : 'bg-amber-500/10 text-amber-600 border-amber-500/20'
                  }`}
                >
                  {item.status}
                </span>
              </div>
              <p className="text-muted-foreground line-clamp-2">{item.payload.content}</p>
              {onConvertToTask && (
                <div className="flex items-center justify-end pt-1 border-t border-border/20">
                  <button
                    type="button"
                    onClick={() => onConvertToTask(item.payload.content)}
                    data-testid={`staging-convert-task-${item.id}`}
                    className="flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium text-primary hover:bg-primary/10 transition-colors cursor-pointer"
                  >
                    <Send className="w-2.5 h-2.5" />
                    <span>{convertToTaskLabel || '派发任务'}</span>
                  </button>
                </div>
              )}
            </div>
          );
        })
      )}
    </div>
  );
};
