/**
 * Proactive Past-Pitfall Non-Intrusive Alert Callout View.
 * Displays high-visibility advisory banners for severe architecture pitfalls with one-click actions.
 */

import React from 'react';
import {
  AlertTriangle,
  Lightbulb,
  Check,
  BellOff,
  BellRing,
  History,
  TrendingUp,
} from 'lucide-react';
import { PitfallAlertCardDTO } from '@/services/memory/decisionAssist';

interface ProactivePitfallCalloutViewProps {
  alertCard: PitfallAlertCardDTO | null;
  onAdoptSuggestion?: (action: string) => void;
  onMuteTopic?: (subject: string) => void;
  onUnmuteTopic?: (subject: string) => void;
  isMuted?: boolean;
}

export const ProactivePitfallCalloutView: React.FC<ProactivePitfallCalloutViewProps> = ({
  alertCard,
  onAdoptSuggestion,
  onMuteTopic,
  onUnmuteTopic,
  isMuted = false,
}) => {
  if (!alertCard) {
    return (
      <section className="bg-card/40 border border-dashed border-border/60 rounded-xl p-6 text-center space-y-2">
        <div className="w-9 h-9 rounded-full bg-muted/60 text-muted-foreground flex items-center justify-center mx-auto">
          <Lightbulb className="w-4 h-4 text-emerald-500/80" />
        </div>
        <div className="text-xs font-semibold text-foreground">暂无主动风险预警</div>
        <p className="text-xs text-muted-foreground max-w-sm mx-auto">
          当前输入或技术上下文运行平稳。当检测到重大技术选型且命中历史故障复盘时，系统将在此呈现实时警报。
        </p>
      </section>
    );
  }

  const isCritical = alertCard.severity === 'critical';

  return (
    <article
      className={`border rounded-xl p-4 shadow-sm space-y-3.5 transition-all ${
        isCritical
          ? 'bg-rose-500/5 border-rose-500/30'
          : 'bg-amber-500/5 border-amber-500/30'
      }`}
    >
      {/* Header with Severity Badge */}
      <header className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <div
            className={`p-2 rounded-lg ${
              isCritical
                ? 'bg-rose-500/15 text-rose-500'
                : 'bg-amber-500/15 text-amber-500'
            }`}
          >
            <AlertTriangle className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold tracking-tight text-foreground">
                历史踩坑与决策干预预警
              </span>
              <span
                className={`text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider ${
                  isCritical
                    ? 'bg-rose-500/20 text-rose-600 dark:text-rose-400 border border-rose-500/30'
                    : 'bg-amber-500/20 text-amber-600 dark:text-amber-400 border border-amber-500/30'
                }`}
              >
                {alertCard.severity}
              </span>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              目标组件: <strong className="text-foreground">{alertCard.subject}</strong>
            </p>
          </div>
        </div>

        {/* Source Anchor */}
        {alertCard.source_ref && (
          <span className="text-[11px] text-muted-foreground flex items-center gap-1 bg-background/50 px-2 py-1 rounded-md border border-border/40">
            <History className="w-3 h-3 text-primary/70" />
            {alertCard.source_ref}
          </span>
        )}
      </header>

      {/* Decision Summary */}
      <div className="p-2.5 rounded-lg bg-background/60 border border-border/50 text-xs">
        <span className="font-medium text-muted-foreground">拟定决策: </span>
        <span className="font-semibold text-foreground">{alertCard.intent_summary}</span>
      </div>

      {/* Historical Pitfall Lesson */}
      <div className="space-y-1">
        <div className="text-xs font-semibold text-rose-500 flex items-center gap-1">
          <span>💥 历史惨痛教训与根因复盘:</span>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed pl-3 border-l-2 border-rose-500/40">
          {alertCard.historical_pitfall}
        </p>
      </div>

      {/* Recommended Alternative */}
      <div className="space-y-1">
        <div className="text-xs font-semibold text-emerald-500 flex items-center gap-1">
          <Lightbulb className="w-3.5 h-3.5" />
          <span>✅ 经受检验的推荐替代方案:</span>
        </div>
        <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-xs text-foreground font-medium leading-relaxed">
          {alertCard.recommended_action}
        </div>
      </div>

      {/* Runtime Version Drift Warning if present */}
      {alertCard.drift_warning && (
        <div className="p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-xs text-amber-600 dark:text-amber-400 flex items-start gap-2">
          <TrendingUp className="w-3.5 h-3.5 shrink-0 mt-0.5" />
          <span className="leading-snug">{alertCard.drift_warning}</span>
        </div>
      )}

      {/* Actions Toolbar */}
      <footer className="pt-2 flex flex-wrap items-center justify-between gap-2 border-t border-border/40">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onAdoptSuggestion?.(alertCard.recommended_action)}
            className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white transition-colors flex items-center gap-1.5 focus:outline-hidden focus:ring-2 focus:ring-primary shadow-xs"
          >
            <Check className="w-3.5 h-3.5" />
            采纳此建议
          </button>
        </div>

        <div className="flex items-center gap-2">
          {isMuted ? (
            <button
              type="button"
              onClick={() => onUnmuteTopic?.(alertCard.subject)}
              className="text-xs px-2.5 py-1.5 rounded-lg bg-muted text-muted-foreground hover:text-foreground transition-colors border border-border/60 flex items-center gap-1 focus:outline-hidden focus:ring-2 focus:ring-primary"
            >
              <BellRing className="w-3.5 h-3.5 text-sky-500" />
              恢复此主题预警
            </button>
          ) : (
            <button
              type="button"
              onClick={() => onMuteTopic?.(alertCard.subject)}
              className="text-xs px-2.5 py-1.5 rounded-lg bg-muted/60 text-muted-foreground hover:text-foreground transition-colors border border-border/40 flex items-center gap-1 focus:outline-hidden focus:ring-2 focus:ring-primary"
            >
              <BellOff className="w-3.5 h-3.5 text-muted-foreground" />
              本会话对此方案静音
            </button>
          )}
        </div>
      </footer>
    </article>
  );
};
