'use client';

import React from 'react';
import { Badge } from '@/components/primitives/badge';
import { CheckCircle2, ShieldAlert, History, ShieldCheck } from 'lucide-react';
import type {
  EpochStatusResponseDTO,
  ExtractedFactCandidateDTO,
} from '@/services/memory/noiseFreeMemory';

interface NoiseFreeMemoryEpochViewProps {
  status: EpochStatusResponseDTO | null;
  facts: ExtractedFactCandidateDTO[];
}

export function NoiseFreeMemoryEpochView({
  status,
  facts,
}: NoiseFreeMemoryEpochViewProps): React.JSX.Element {
  return (
    <div className="space-y-3" data-testid="noise-free-epoch-view">
      {/* HUD Metrics Banner */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
        <div className="rounded-md border border-border/70 p-2.5 bg-card">
          <div className="text-[11px] text-muted-foreground flex items-center gap-1">
            <History className="h-3 w-3 text-primary" />
            <span>当前代次 (Epoch)</span>
          </div>
          <div className="text-lg font-bold text-primary" data-testid="current-epoch-hud">
            Gen {status?.current_generation ?? 1}
          </div>
        </div>

        <div className="rounded-md border border-border/70 p-2.5 bg-card">
          <div className="text-[11px] text-muted-foreground flex items-center gap-1">
            <ShieldCheck className="h-3 w-3 text-green-500" />
            <span>有效事实存储</span>
          </div>
          <div className="text-lg font-bold text-foreground">
            {facts.length} 条
          </div>
        </div>

        <div className="rounded-md border border-border/70 p-2.5 bg-card">
          <div className="text-[11px] text-muted-foreground flex items-center gap-1">
            <ShieldAlert className="h-3 w-3 text-destructive" />
            <span>幽灵写入丢弃 (Fenced)</span>
          </div>
          <div className="text-lg font-bold text-amber-600 dark:text-amber-400">
            {status?.stale_writes_dropped ?? 0}
          </div>
        </div>

        <div className="rounded-md border border-border/70 p-2.5 bg-card">
          <div className="text-[11px] text-muted-foreground flex items-center gap-1">
            <ShieldAlert className="h-3 w-3 text-destructive" />
            <span>PII 违规阻断</span>
          </div>
          <div className="text-lg font-bold text-destructive">
            {status?.pii_violations_blocked ?? 0}
          </div>
        </div>
      </div>

      {/* Persisted Clean Facts List */}
      <div className="rounded-md border border-border/70 p-3 bg-card space-y-2 text-xs">
        <div className="font-semibold text-foreground flex items-center justify-between">
          <span className="flex items-center gap-1.5">
            <CheckCircle2 className="h-4 w-4 text-green-500" />
            <span>当前代次已持久化纯净事实 ({facts.length})</span>
          </span>
          <span className="text-[11px] text-muted-foreground">
            {status?.last_purged_at ? `上次 Purge: ${status.last_purged_at.slice(0, 19).replace('T', ' ')}` : '未发生过 Purge'}
          </span>
        </div>

        <div className="space-y-1.5 max-h-40 overflow-y-auto">
          {facts.length > 0 ? (
            facts.map((fact) => (
              <div
                key={fact.fact_id}
                className="rounded border border-border/50 p-2 bg-background flex items-start justify-between gap-2"
              >
                <div className="space-y-0.5 min-w-0">
                  <div className="text-foreground font-medium truncate">{fact.fact_text}</div>
                  <div className="text-[10px] text-muted-foreground">
                    类别: {fact.category ?? 'user_preference'} · 置信度: {((fact.confidence ?? 0.9) * 100).toFixed(0)}%
                  </div>
                </div>
                <Badge variant="outline" className="text-[9px] py-0 px-1 shrink-0 text-primary border-primary/30">
                  Gen {fact.generation_observed}
                </Badge>
              </div>
            ))
          ) : (
            <div className="text-center py-3 text-muted-foreground text-[11px]">
              当前代次暂无存储的记忆事实（已清空或尚未抽取）
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
