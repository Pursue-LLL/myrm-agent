import React from 'react';
import {
  Clock,
  Zap,
  ArrowRightLeft,
  ShieldCheck,
  Terminal,
  GitCommit,
  User,
} from 'lucide-react';
import { useTurnLineageStore } from './useTurnLineageStore';
import { TurnOriginType } from './turnLineageTypes';
import { filterTurns, getOriginVisualTheme } from './turnLineageEngine';

export const TurnTimelineAuditRail: React.FC = () => {
  const {
    turns,
    filterMode,
    activeTurnId,
    highlightedLineageChain,
    isRailExpanded,
    selectTurn,
  } = useTurnLineageStore();

  if (!isRailExpanded) {
    return null;
  }

  const filteredTurns = filterTurns(turns, filterMode);

  const getOriginNodeIcon = (type: TurnOriginType) => {
    switch (type) {
      case 'cron_job':
        return <Clock className="w-3 h-3 text-purple-400" />;
      case 'webhook_trigger':
        return <Zap className="w-3 h-3 text-amber-400" />;
      case 'subagent_delegation':
        return <ArrowRightLeft className="w-3 h-3 text-indigo-400" />;
      case 'approval_resume':
        return <ShieldCheck className="w-3 h-3 text-emerald-400" />;
      default:
        return <User className="w-3 h-3 text-slate-400" />;
    }
  };

  return (
    <aside
      data-testid="turn-timeline-audit-rail"
      aria-label="时序因果溯源时间轴"
      className="w-72 bg-slate-950/95 border-l border-slate-800 p-3.5 flex flex-col justify-between select-none overflow-hidden h-full"
    >
      <div>
        {/* 顶部标题 */}
        <div className="flex items-center justify-between pb-2 mb-3 border-b border-slate-800 text-xs">
          <div className="flex items-center gap-1.5 font-semibold text-slate-200">
            <GitCommit className="w-4 h-4 text-indigo-400" />
            <span>时序因果时间轴</span>
          </div>
          <span className="text-[10px] font-mono text-slate-500">
            {filteredTurns.length} 节点
          </span>
        </div>

        {/* 垂直时间线节点列表 */}
        <div className="space-y-3 overflow-y-auto max-h-[500px] pr-1 relative">
          {/* 贯穿垂直连接虚线 */}
          <div className="absolute left-3.5 top-2 bottom-2 w-px bg-slate-800 -z-0" />

          {filteredTurns.map((turn) => {
            const isSelected = activeTurnId === turn.id;
            const isInChain = highlightedLineageChain.includes(turn.id);
            const theme = getOriginVisualTheme(turn.provenance.originType);

            return (
              <button
                key={turn.id}
                type="button"
                onClick={() => selectTurn(turn.id)}
                className={`w-full text-left relative z-10 flex items-start gap-2.5 p-2 rounded-xl border transition-all cursor-pointer ${
                  isSelected
                    ? 'bg-indigo-950/70 border-indigo-500 shadow-md ring-1 ring-indigo-500/50'
                    : isInChain
                    ? 'bg-slate-900/90 border-indigo-500/40'
                    : 'bg-slate-900/40 border-slate-800/80 hover:bg-slate-900 hover:border-slate-700'
                }`}
              >
                {/* 节点图标指示 */}
                <div
                  className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0 border mt-0.5 ${
                    isSelected
                      ? 'bg-indigo-600 border-indigo-400 text-white'
                      : 'bg-slate-900 border-slate-700 text-slate-400'
                  }`}
                >
                  {getOriginNodeIcon(turn.provenance.originType)}
                </div>

                {/* 节点文字与因果线索 */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="font-bold font-mono text-slate-200">
                      #{turn.turnNumber} {turn.author}
                    </span>
                    <span className="text-[10px] font-mono text-slate-500">
                      {turn.provenance.timestamp}
                    </span>
                  </div>

                  <p className="mt-0.5 text-[11px] text-slate-400 line-clamp-2 leading-tight">
                    {turn.content}
                  </p>

                  <div className="mt-1 flex items-center gap-1.5 text-[9px]">
                    <span
                      className={`px-1.5 py-0.2 rounded border font-medium ${theme.badgeBg} ${theme.badgeBorder} ${theme.badgeText}`}
                    >
                      {theme.label}
                    </span>
                    {turn.provenance.causalityParentId && (
                      <span className="text-indigo-400 font-mono">
                        ← {turn.provenance.causalityParentId}
                      </span>
                    )}
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* 底部因果追溯说明 */}
      <div className="pt-2 border-t border-slate-800/80 text-[10px] text-slate-500 font-mono flex items-center justify-between">
        <span className="truncate max-w-[170px]">
          {highlightedLineageChain.length > 0
            ? `因果链: ${highlightedLineageChain.join(' → ')}`
            : '点击节点高亮因果链路'}
        </span>
        <Terminal className="w-3 h-3 text-slate-600 shrink-0" />
      </div>
    </aside>
  );
};
