'use client';

import React from 'react';
import { Badge } from '@/components/primitives/badge';
import { Clock, Zap } from 'lucide-react';
import type {
  MacroMilestoneFoldDTO,
  MicroActivitySliceDTO,
} from '@/services/memory/activityCompactor';

interface ActivityCompactorTimelineViewProps {
  microSlices: MicroActivitySliceDTO[];
  macroFolds: MacroMilestoneFoldDTO[];
}

export function ActivityCompactorTimelineView({
  microSlices,
  macroFolds,
}: ActivityCompactorTimelineViewProps): React.JSX.Element {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs" data-testid="activity-compactor-timeline-view">
      {/* Micro Slices List */}
      <div className="space-y-1.5 rounded-md border border-border/70 p-2.5 bg-card">
        <span className="font-semibold text-foreground flex items-center gap-1">
          <Zap className="h-3.5 w-3.5 text-primary" />
          <span>最近 10 分钟微观算法折叠切片</span>
        </span>
        <div className="space-y-1 max-h-36 overflow-y-auto">
          {microSlices.length > 0 ? (
            microSlices.map((s) => (
              <div key={s.slice_id} className="rounded border border-border/50 p-1.5 bg-background text-[11px]">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-foreground">[{s.primary_app}]</span>
                  <Badge variant="outline" className="text-[9px] py-0 px-1">
                    {s.raw_event_count} 事件
                  </Badge>
                </div>
                <div className="text-muted-foreground truncate pt-0.5">{s.folded_summary}</div>
              </div>
            ))
          ) : (
            <div className="text-center py-2 text-muted-foreground text-[11px]">暂无微观折叠切片</div>
          )}
        </div>
      </div>

      {/* Macro Folds List */}
      <div className="space-y-1.5 rounded-md border border-border/70 p-2.5 bg-card">
        <span className="font-semibold text-foreground flex items-center gap-1">
          <Clock className="h-3.5 w-3.5 text-green-600" />
          <span>最近 6 小时宏观业务里程碑</span>
        </span>
        <div className="space-y-1 max-h-36 overflow-y-auto">
          {macroFolds.length > 0 ? (
            macroFolds.map((f) => (
              <div key={f.fold_id} className="rounded border border-green-500/30 p-1.5 bg-background text-[11px]">
                <div className="flex items-center justify-between text-green-700 dark:text-green-400 font-semibold">
                  <span>6h 宏观提纯</span>
                  <div className="flex gap-1">
                    {f.tags.map((t) => (
                      <Badge key={t} variant="secondary" className="text-[8px] py-0 px-1">
                        {t}
                      </Badge>
                    ))}
                  </div>
                </div>
                <div className="text-foreground truncate pt-0.5">{f.milestone_summary}</div>
              </div>
            ))
          ) : (
            <div className="text-center py-2 text-muted-foreground text-[11px]">暂无宏观里程碑</div>
          )}
        </div>
      </div>
    </div>
  );
}
