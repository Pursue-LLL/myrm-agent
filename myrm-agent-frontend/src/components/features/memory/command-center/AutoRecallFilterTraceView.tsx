/**
 * [INPUT]
 * - @/services/memory/autoRecall: AutoRecallDecisionResponse
 * - @/components/primitives/badge: Badge
 *
 * [OUTPUT]
 * - AutoRecallFilterTraceView: Sub-component rendering auto-recall trigger decision, sliding dedup stats, and injected items.
 *
 * [POS]
 * Sub-component for AutoRecallGovernanceCard under command-center.
 * Strict typing applied: No `any` types allowed.
 */

'use client';

import React from 'react';
import {
  CheckCircle2,
  Clock,
  Filter,
  Layers,
  ShieldCheck,
  Sparkles,
  XCircle,
} from 'lucide-react';

import { Badge } from '@/components/primitives/badge';
import type { AutoRecallDecisionResponse } from '@/services/memory/autoRecall';

interface AutoRecallFilterTraceViewProps {
  decision: AutoRecallDecisionResponse | null;
}

function getTriggerBadge(triggerType: string, triggered: boolean): { label: string; className: string } {
  if (!triggered || triggerType === 'none') {
    return {
      label: '完全抑制 (0 召回)',
      className: 'border-muted-foreground/40 text-muted-foreground bg-muted/20',
    };
  }
  const map: Record<string, string> = {
    task_start: '任务启动 (task_start)',
    skill_load: '技能加载 (skill_load)',
    subagent_start: '子智能体派发 (subagent_start)',
    write_preflight: '高危写前防护 (write_preflight)',
    cron_start: '定时心跳激活 (cron_start)',
  };
  return {
    label: map[triggerType] || triggerType,
    className: 'border-primary/40 text-primary bg-primary/10',
  };
}

function getRerankerStatusBadge(status: string): { label: string; className: string } {
  switch (status) {
    case 'applied':
      return {
        label: '神经重排完成',
        className: 'border-emerald-500/40 text-emerald-600 dark:text-emerald-400 bg-emerald-500/10',
      };
    case 'reranker_skipped':
      return {
        label: '无 Key 静默跳过 (Fail-Open)',
        className: 'border-blue-500/40 text-blue-600 dark:text-blue-400 bg-blue-500/10',
      };
    case 'timed_out':
      return {
        label: '超时降级粗排 (>800ms)',
        className: 'border-amber-500/40 text-amber-600 dark:text-amber-400 bg-amber-500/10',
      };
    default:
      return {
        label: '异常熔断放行 (Fail-Open)',
        className: 'border-destructive/40 text-destructive bg-destructive/10',
      };
  }
}

export function AutoRecallFilterTraceView({ decision }: AutoRecallFilterTraceViewProps) {
  if (!decision) {
    return (
      <div className="rounded border border-dashed border-border/60 p-4 text-center text-xs text-muted-foreground">
        暂无自动召回决策记录，请配置参数并执行探针评估
      </div>
    );
  }

  const triggerBadge = getTriggerBadge(decision.trigger_type, decision.triggered);
  const rerankerBadge = getRerankerStatusBadge(decision.reranker_status);

  return (
    <div className="space-y-3">
      {/* 审计决策概览条 */}
      <div className="rounded-md border border-border/70 bg-card p-3 text-xs space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/50 pb-2">
          <div className="flex items-center gap-1.5 font-medium">
            <ShieldCheck className="h-4 w-4 text-primary" />
            <span>门禁审计裁决</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Badge variant="outline" className={triggerBadge.className}>
              {triggerBadge.label}
            </Badge>
            <Badge variant="outline" className={rerankerBadge.className}>
              {rerankerBadge.label}
            </Badge>
          </div>
        </div>

        {/* 过滤统计漏斗 */}
        <div className="grid grid-cols-3 gap-2 py-1 text-center font-mono">
          <div className="rounded bg-muted/40 p-1.5">
            <div className="text-[10px] text-muted-foreground">召回候选总数</div>
            <div className="font-semibold text-foreground">{decision.candidates_pre_dedup}</div>
          </div>
          <div className="rounded bg-muted/40 p-1.5">
            <div className="text-[10px] text-muted-foreground">5 轮滑窗存活数</div>
            <div className="font-semibold text-primary">{decision.candidates_post_dedup}</div>
          </div>
          <div className="rounded bg-muted/40 p-1.5">
            <div className="text-[10px] text-muted-foreground">最终注入记忆数</div>
            <div className="font-semibold text-emerald-600 dark:text-emerald-400">
              {decision.injected_candidates.length}
            </div>
          </div>
        </div>

        <div className="text-[11px] text-muted-foreground">
          <strong>审计说明:</strong> {decision.audit_reason}
        </div>
      </div>

      {/* 注入记忆清单 */}
      {decision.injected_candidates.length > 0 && (
        <div className="space-y-2">
          <div className="text-[11px] font-medium text-muted-foreground flex items-center justify-between">
            <span>已通过门禁并注入 Context 的经验记忆 ({decision.injected_candidates.length})</span>
          </div>
          <div className="max-h-48 space-y-2 overflow-y-auto pr-1">
            {decision.injected_candidates.map((cand) => (
              <div
                key={cand.memory_id}
                className="rounded border border-border/70 bg-card p-2 text-xs"
              >
                <div className="flex items-center justify-between font-mono text-[11px] text-foreground">
                  <span className="font-semibold">{cand.memory_id}</span>
                  {cand.initial_score !== undefined && (
                    <span className="text-[10px] text-muted-foreground">
                      打分: {cand.initial_score.toFixed(2)}
                    </span>
                  )}
                </div>
                <div className="mt-1 text-muted-foreground leading-relaxed">
                  {cand.content}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
