/**
 * [INPUT]
 * - @/services/memory/decayLifecycle: ColdArchiveItemSchema
 * - @/components/primitives/badge: Badge
 *
 * [OUTPUT]
 * - ColdArchiveRecordsView: Sub-component rendering archived cold memory entries with scores and timestamps.
 *
 * [POS]
 * Sub-component for EbbinghausLifecycleCard under command-center.
 * Strict typing applied: No `any` types allowed.
 */

'use client';

import React from 'react';
import { Archive, Clock, Pin } from 'lucide-react';

import { Badge } from '@/components/primitives/badge';
import type { ColdArchiveItemSchema } from '@/services/memory/decayLifecycle';

interface ColdArchiveRecordsViewProps {
  records: ColdArchiveItemSchema[];
}

export function ColdArchiveRecordsView({ records }: ColdArchiveRecordsViewProps) {
  if (records.length === 0) {
    return (
      <div className="rounded border border-dashed border-border/60 p-4 text-center text-xs text-muted-foreground">
        暂无冷存储归档条目
      </div>
    );
  }

  return (
    <div className="max-h-48 space-y-1.5 overflow-y-auto pr-1">
      {records.map((rec) => (
        <div
          key={rec.memory_id}
          className="rounded border border-border/50 bg-accent/15 p-2 text-xs transition hover:bg-accent/25"
        >
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5">
                <Archive className="h-3.5 w-3.5 text-blue-400" />
                <span className="font-mono text-[11px] font-semibold text-foreground">
                  {rec.memory_id}
                </span>
                {rec.pinned && (
                  <Pin className="h-3 w-3 text-amber-500" />
                )}
                <Badge variant="outline" className="px-1.5 py-0 text-[9px]">
                  {rec.tier}
                </Badge>
              </div>
              <p className="mt-1 line-clamp-2 text-muted-foreground">
                {rec.content}
              </p>
            </div>
            <div className="shrink-0 text-right text-[10px] text-muted-foreground">
              <div>衰减分: <strong className="text-foreground">{rec.score}</strong></div>
              <div>访问: {rec.access_count}次</div>
              <div className="mt-0.5 flex items-center justify-end gap-1">
                <Clock className="h-2.5 w-2.5" />
                <span>{new Date(rec.last_accessed_at * 1000).toLocaleDateString()}</span>
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
