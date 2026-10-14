'use client';

import React, { useMemo } from 'react';
import { useTranslations } from 'next-intl';
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  Clock,
  Coins,
  Gauge,
  Lightbulb,
  ShieldAlert,
  Sparkles,
  Zap,
} from 'lucide-react';
import { Card } from '@/components/primitives/card';
import { Badge } from '@/components/primitives/badge';
import { fmtCost, fmtTokens, extractCostUsd, extractTotalTokens } from '@/lib/utils/subagent/subagentTree';
import type { SubagentNode } from '@/store/chat/useSubagentStore';
import { activateOnKey } from '@/lib/utils/a11y';

interface SubagentInsightsViewProps {
  nodes: Record<string, SubagentNode> | SubagentNode[];
  onSelectNode?: (taskId: string) => void;
}

/** 并行子任务数超过该值时，建议最终汇总步骤合并各路输出，避免上下文溢出。 */
const HIGH_FAN_OUT_THRESHOLD = 15;

interface AgentTypeStat {
  agentType: string;
  count: number;
  totalDuration: number;
  avgDuration: number;
  totalCostUsd: number;
  totalTokens: number;
  failedCount: number;
}

export const SubagentInsightsView: React.FC<SubagentInsightsViewProps> = ({ nodes, onSelectNode }) => {
  const t = useTranslations('subagentDashboard');
  const nodeList = useMemo(() => (Array.isArray(nodes) ? nodes : Object.values(nodes)), [nodes]);
  const visibleNodes = useMemo(() => nodeList.filter((n) => !n.internal), [nodeList]);

  // Aggregate stats by agent type
  const typeStats = useMemo<Record<string, AgentTypeStat>>(() => {
    const stats: Record<string, AgentTypeStat> = {};

    for (const node of visibleNodes) {
      const type = node.agent_type || 'default';
      if (!stats[type]) {
        stats[type] = {
          agentType: type,
          count: 0,
          totalDuration: 0,
          avgDuration: 0,
          totalCostUsd: 0,
          totalTokens: 0,
          failedCount: 0,
        };
      }
      stats[type].count += 1;
      stats[type].totalDuration += node.duration_seconds || 0;
      stats[type].totalCostUsd += extractCostUsd(node);
      stats[type].totalTokens += extractTotalTokens(node);
      if (node.status === 'failed' || node.status === 'timed_out') {
        stats[type].failedCount += 1;
      }
    }

    for (const key of Object.keys(stats)) {
      stats[key].avgDuration = stats[key].count > 0 ? stats[key].totalDuration / stats[key].count : 0;
    }

    return stats;
  }, [visibleNodes]);

  // 异常节点：卡住、耗时超过同类型均值 2 倍且大于 30s、被预算或超时守卫中止
  const anomalies = useMemo(() => {
    const list: { node: SubagentNode; reason: string; severity: 'warning' | 'danger' }[] = [];

    for (const node of visibleNodes) {
      const type = node.agent_type || 'default';
      const stat = typeStats[type];
      const duration = node.duration_seconds || 0;

      if (node.stale) {
        list.push({
          node,
          reason: t('insightsAnomalyStalled', { seconds: node.staleDurationSeconds || 0 }),
          severity: 'danger',
        });
      } else if (stat && stat.count >= 2 && duration > stat.avgDuration * 2 && duration > 30) {
        list.push({
          node,
          reason: t('insightsAnomalySlow', { duration, average: Math.round(stat.avgDuration), type }),
          severity: 'warning',
        });
      } else if (node.status === 'timed_out' || node.status === 'cancelled_by_budget') {
        list.push({
          node,
          reason: t('insightsAnomalyAborted'),
          severity: 'danger',
        });
      }
    }

    return list;
  }, [visibleNodes, typeStats, t]);

  // 面向用户的优化建议
  const loopGuardSuggestions = useMemo(() => {
    const suggestions: string[] = [];

    if (anomalies.some((a) => a.node.stale)) {
      suggestions.push(t('insightsAdviceStalled'));
    }

    const failedVerifications = visibleNodes.filter((n) => n.verification && !n.verification.passed);
    if (failedVerifications.length > 0) {
      suggestions.push(t('insightsAdviceVerification', { count: failedVerifications.length }));
    }

    if (visibleNodes.length > HIGH_FAN_OUT_THRESHOLD) {
      suggestions.push(t('insightsAdviceFanOut', { limit: HIGH_FAN_OUT_THRESHOLD }));
    }

    return suggestions;
  }, [anomalies, visibleNodes, t]);

  if (visibleNodes.length === 0) {
    return <div className="py-12 text-center text-xs text-muted-foreground">{t('insightsEmpty')}</div>;
  }

  return (
    <div className="space-y-4 text-xs" data-testid="subagent-insights-view">
      {/* 优化建议 */}
      {loopGuardSuggestions.length > 0 && (
        <div className="p-3.5 rounded-lg bg-amber-50/70 dark:bg-amber-950/20 border border-amber-200/80 dark:border-amber-900/40 text-amber-900 dark:text-amber-200">
          <div className="flex items-center gap-1.5 font-bold mb-2 text-xs">
            <Lightbulb className="w-4 h-4 text-amber-600 dark:text-amber-400" />
            <span>{t('insightsAdviceTitle')}</span>
          </div>
          <ul className="space-y-1 text-[11px] list-disc list-inside">
            {loopGuardSuggestions.map((s, idx) => (
              <li key={idx} className="leading-relaxed">
                {s}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Anomalies & Outliers */}
      <div>
        <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-1.5">
          <AlertTriangle className="w-3.5 h-3.5 text-orange-500" />
          <span>{t('insightsAnomaliesTitle', { count: anomalies.length })}</span>
        </h4>

        {anomalies.length === 0 ? (
          <div className="p-3 rounded-lg border bg-muted/20 text-muted-foreground text-center text-[11px]">
            {t('insightsAnomaliesEmpty')}
          </div>
        ) : (
          <div className="space-y-1.5">
            {anomalies.map((item, idx) => (
              <div
                key={idx}
                onClick={() => onSelectNode && onSelectNode(item.node.task_id)}
                role="button"
                tabIndex={0}
                onKeyDown={activateOnKey}
                className={`p-2.5 rounded-lg border text-xs flex items-center justify-between gap-3 cursor-pointer transition-colors ${
                  item.severity === 'danger'
                    ? 'bg-red-50/40 dark:bg-red-950/20 border-red-200 dark:border-red-900/50 hover:bg-red-50/80'
                    : 'bg-amber-50/40 dark:bg-amber-950/20 border-amber-200 dark:border-amber-900/50 hover:bg-amber-50/80'
                }`}
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2 font-medium">
                    <Badge variant="outline" className="text-[10px] font-mono">
                      {item.node.agent_type || t('detailFallbackAgentType')}
                    </Badge>
                    <span className="truncate">{item.reason}</span>
                  </div>
                </div>
                <span className="font-mono text-[10px] text-muted-foreground shrink-0">
                  {item.node.duration_seconds || 0}s
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 按子任务类型的性能基线 */}
      <div>
        <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-1.5">
          <Gauge className="w-3.5 h-3.5 text-primary" />
          <span>{t('insightsTypePerformance')}</span>
        </h4>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {Object.values(typeStats).map((stat) => (
            <div key={stat.agentType} className="p-3 rounded-lg border bg-muted/20 space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-foreground text-xs">{stat.agentType}</span>
                <Badge variant="secondary" className="text-[10px]">
                  {t('insightsSpawned', { count: stat.count })}
                </Badge>
              </div>
              <div className="grid grid-cols-3 gap-1 text-[11px] text-muted-foreground pt-1 border-t border-border/40">
                <div>
                  <span className="text-[9px] block opacity-70">{t('insightsAvgDuration')}</span>
                  <span className="font-semibold text-foreground">{Math.round(stat.avgDuration)}s</span>
                </div>
                <div>
                  <span className="text-[9px] block opacity-70">{t('insightsTotalTokens')}</span>
                  <span className="font-semibold text-foreground">{fmtTokens(stat.totalTokens)}</span>
                </div>
                <div>
                  <span className="text-[9px] block opacity-70">{t('insightsTotalCost')}</span>
                  <span className="font-semibold text-foreground">{fmtCost(stat.totalCostUsd) || '$0'}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default SubagentInsightsView;
