import React from 'react';
import {
  Clock,
  Zap,
  ArrowRightLeft,
  ShieldCheck,
  Terminal,
  Cpu,
  GitFork,
  Tag,
} from 'lucide-react';
import { TurnProvenanceMeta, TurnOriginType } from './turnLineageTypes';
import { getOriginVisualTheme } from './turnLineageEngine';

interface TurnProvenanceHoverCardProps {
  provenance: TurnProvenanceMeta;
  tokensUsed?: number;
  durationMs?: number;
}

export const TurnProvenanceHoverCard: React.FC<TurnProvenanceHoverCardProps> = ({
  provenance,
  tokensUsed,
  durationMs,
}) => {
  const theme = getOriginVisualTheme(provenance.originType);

  const getOriginIcon = (type: TurnOriginType) => {
    switch (type) {
      case 'cron_job':
        return <Clock className="w-3.5 h-3.5 text-purple-400" />;
      case 'webhook_trigger':
        return <Zap className="w-3.5 h-3.5 text-amber-400" />;
      case 'subagent_delegation':
        return <ArrowRightLeft className="w-3.5 h-3.5 text-indigo-400" />;
      case 'approval_resume':
        return <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />;
      default:
        return <Terminal className="w-3.5 h-3.5 text-slate-400" />;
    }
  };

  return (
    <div
      data-testid="turn-provenance-hover-card"
      className="w-72 bg-slate-950/95 backdrop-blur-md border border-slate-800 rounded-2xl p-3.5 shadow-2xl text-slate-200 select-none animate-in fade-in zoom-in-95 duration-100 z-30"
    >
      {/* 头部触发源大类 */}
      <div className="flex items-center justify-between pb-2 mb-2 border-b border-slate-800">
        <div className="flex items-center gap-1.5 text-xs font-semibold">
          {getOriginIcon(provenance.originType)}
          <span className={theme.badgeText}>{theme.label}</span>
        </div>
        <span className="text-[10px] font-mono text-slate-500">
          {provenance.timestamp}
        </span>
      </div>

      {/* 详细触发说明 */}
      <div className="space-y-1.5 text-xs">
        <div>
          <span className="text-[10px] text-slate-500">触发源：</span>
          <p className="font-medium text-slate-100 text-[11px] leading-snug">
            {provenance.triggerSourceTitle}
          </p>
        </div>

        <div className="flex items-center justify-between text-[11px] text-slate-400 pt-1">
          <span className="inline-flex items-center gap-1">
            <Cpu className="w-3 h-3 text-indigo-400" />
            <span>执行者: {provenance.executedByAgent}</span>
          </span>
          <span className="font-mono text-[10px] text-slate-500">
            ID: {provenance.originRefId}
          </span>
        </div>

        {provenance.causalityParentId && (
          <div className="flex items-center gap-1 text-[10px] text-indigo-300 pt-0.5">
            <GitFork className="w-3 h-3 text-indigo-400 shrink-0" />
            <span>前序上游: {provenance.causalityParentId}</span>
          </div>
        )}

        {provenance.details && (
          <div className="mt-1.5 p-2 bg-slate-900/80 rounded-xl border border-slate-800/80 text-[10px] font-mono space-y-0.5 text-slate-400">
            {Object.entries(provenance.details).map(([k, v]) => (
              <div key={k} className="flex items-center justify-between">
                <span className="text-slate-500">{k}:</span>
                <span className="text-slate-300 truncate max-w-[170px]">{v}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 性能开销指标 */}
      {(typeof tokensUsed === 'number' || typeof durationMs === 'number') && (
        <div className="mt-2.5 pt-2 border-t border-slate-800/80 flex items-center justify-between text-[10px] text-slate-500 font-mono">
          <div className="flex items-center gap-1">
            <Tag className="w-3 h-3 text-slate-600" />
            <span>Token: {tokensUsed || 0} T</span>
          </div>
          <span>耗时: {durationMs || 0}ms</span>
        </div>
      )}
    </div>
  );
};
