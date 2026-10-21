'use client';

/**
 * [INPUT]
 * - @/store/chat/types/messages::CouncilResultView (POS: 多专家 Council 编排结构化会商结果数据模型)
 * - next-intl::useTranslations
 *
 * [OUTPUT]
 * - CouncilResultCard: 结构化多专家交叉质询与首席仲裁折叠渲染卡片
 *
 * [POS]
 * MessageItem/ChatWindow 消息流中专用于呈现多专家三阶段会商（独立分析 -> 交叉反驳 -> 首席仲裁）的直观可视化组件。
 */

import React, { memo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Users, CheckCircle2, AlertTriangle, ListOrdered, ChevronDown, ChevronUp, Bot } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import type { CouncilResultView } from '@/store/chat/types/messages';

export interface CouncilResultCardProps {
  councilResult: CouncilResultView;
  className?: string;
}

export const CouncilResultCard = memo(function CouncilResultCard({ councilResult, className }: CouncilResultCardProps) {
  const t = useTranslations('expertSummon');
  const [expanded, setExpanded] = useState(false);

  const {
    synthesis,
    consensus_points = [],
    divergences = [],
    action_items = [],
    opinions = [],
    rounds_completed = 0,
    total_duration_seconds,
  } = councilResult;

  return (
    <div
      data-testid="council-result-card"
      className={cn(
        'my-3 rounded-xl border border-primary/20 bg-gradient-to-b from-primary/5 via-card to-card p-4 shadow-sm text-sm',
        className,
      )}
    >
      {/* 头部状态与标题 */}
      <div className="flex items-center justify-between pb-3 border-b border-border/50">
        <div className="flex items-center gap-2 font-medium text-foreground">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Users className="h-4 w-4" />
          </div>
          <span>{t('councilResultTitle')}</span>
          {rounds_completed > 0 && (
            <span className="rounded-full bg-secondary px-2 py-0.5 text-xs text-muted-foreground font-normal">
              {t('roundLabel', { round: rounds_completed })}
            </span>
          )}
        </div>
        {total_duration_seconds !== undefined && total_duration_seconds > 0 && (
          <span className="text-xs text-muted-foreground">{total_duration_seconds.toFixed(1)}s</span>
        )}
      </div>

      {/* 首席仲裁方案核心展示 */}
      {synthesis && (
        <div className="mt-3 space-y-1.5">
          <div className="text-xs font-semibold text-primary uppercase tracking-wider">{t('chairSynthesisTitle')}</div>
          <div className="rounded-lg bg-muted/40 p-3 text-foreground whitespace-pre-wrap leading-relaxed">
            {synthesis}
          </div>
        </div>
      )}

      {/* 共识要点 */}
      {consensus_points.length > 0 && (
        <div className="mt-3 space-y-1">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-emerald-600 dark:text-emerald-400">
            <CheckCircle2 className="h-3.5 w-3.5" />
            <span>{t('consensusPoints')}</span>
          </div>
          <ul className="list-disc pl-5 space-y-0.5 text-xs text-muted-foreground">
            {consensus_points.map((point, idx) => (
              <li key={idx}>{point}</li>
            ))}
          </ul>
        </div>
      )}

      {/* 分歧辩论点 */}
      {divergences.length > 0 && (
        <div className="mt-3 space-y-1">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-amber-600 dark:text-amber-400">
            <AlertTriangle className="h-3.5 w-3.5" />
            <span>{t('divergences')}</span>
          </div>
          <ul className="list-disc pl-5 space-y-0.5 text-xs text-muted-foreground">
            {divergences.map((div, idx) => (
              <li key={idx}>{div}</li>
            ))}
          </ul>
        </div>
      )}

      {/* 后续执行路线 */}
      {action_items.length > 0 && (
        <div className="mt-3 space-y-1">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-sky-600 dark:text-sky-400">
            <ListOrdered className="h-3.5 w-3.5" />
            <span>{t('actionItems')}</span>
          </div>
          <ol className="list-decimal pl-5 space-y-0.5 text-xs text-muted-foreground">
            {action_items.map((item, idx) => (
              <li key={idx}>{item}</li>
            ))}
          </ol>
        </div>
      )}

      {/* 各专家独立观点与交叉反驳折叠面板 */}
      {opinions.length > 0 && (
        <div className="mt-4 pt-3 border-t border-border/40">
          <button
            type="button"
            data-testid="toggle-expert-opinions-btn"
            onClick={() => setExpanded(!expanded)}
            className="flex items-center justify-between w-full py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
          >
            <span>{expanded ? t('collapseOpinions') : t('expandOpinions', { count: opinions.length })}</span>
            {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </button>

          {expanded && (
            <div className="mt-2 space-y-2.5 animate-in fade-in-50 duration-150">
              {opinions.map((op, idx) => (
                <div key={idx} className="rounded-lg border border-border/60 bg-background/80 p-3 text-xs space-y-1">
                  <div className="flex items-center justify-between font-medium text-foreground">
                    <div className="flex items-center gap-1.5">
                      <Bot className="h-3.5 w-3.5 text-primary" />
                      <span>{op.agent_type || op.expert_id}</span>
                      <span className="rounded bg-secondary px-1.5 py-0.2 text-[10px] text-muted-foreground">
                        {t('roundLabel', { round: op.round_num })}
                      </span>
                    </div>
                    {op.duration_seconds !== undefined && op.duration_seconds > 0 && (
                      <span className="text-[10px] text-muted-foreground">{op.duration_seconds.toFixed(1)}s</span>
                    )}
                  </div>
                  <div className="text-muted-foreground whitespace-pre-wrap leading-relaxed">{op.content}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
});
export default CouncilResultCard;
