import React from 'react';
import { Search, ShieldCheck } from 'lucide-react';
import { useSearchAuditStore } from './useSearchAuditStore';
import { SearchAuditSession } from './searchAuditTypes';
import { formatLatency, getScoreTierBadgeColor } from './searchAuditEngine';

export interface SearchAuditEvidenceBadgeProps {
  session: SearchAuditSession;
  initialCitationId?: string;
  variant?: 'compact' | 'full';
  className?: string;
}

export const SearchAuditEvidenceBadge: React.FC<SearchAuditEvidenceBadgeProps> = ({
  session,
  initialCitationId,
  variant = 'compact',
  className = '',
}) => {
  const { openAuditDrawer } = useSearchAuditStore();

  const handleOpen = () => {
    openAuditDrawer(session, initialCitationId);
  };

  const badgeTheme = getScoreTierBadgeColor(session.averageQualityScore);
  const latencyStr = formatLatency(session.totalLatencyMs);

  if (variant === 'compact') {
    return (
      <button
        type="button"
        onClick={handleOpen}
        aria-label="查看全透明检索证据链与100分打分"
        title="查看每一次底层搜索的耗时明细、载荷大小与100分数据源量化矩阵"
        data-testid="search-audit-evidence-badge-compact"
        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-mono border transition-all hover:scale-[1.02] shadow-sm ${badgeTheme.bg} ${badgeTheme.text} ${badgeTheme.border} ${className}`}
      >
        <Search className="w-3 h-3 text-indigo-400" />
        <span className="font-semibold">{session.averageQualityScore}分权威证据链</span>
        <span className="text-zinc-500">·</span>
        <span className="text-zinc-400">{latencyStr}</span>
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={handleOpen}
      aria-label="查看全透明检索证据链与100分打分"
      title="查看每一次底层搜索的耗时明细、载荷大小与100分数据源量化矩阵"
      data-testid="search-audit-evidence-badge-full"
      className={`flex items-center justify-between p-2.5 rounded-xl bg-zinc-950/80 hover:bg-zinc-900 border border-zinc-800 text-left transition-all group w-full ${className}`}
    >
      <div className="flex items-center gap-2 truncate">
        <div className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 shrink-0">
          <ShieldCheck className="w-4 h-4" />
        </div>
        <div className="truncate">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-zinc-200">
              全透明检索证据链
            </span>
            <span
              className={`text-[10px] font-mono font-bold px-1.5 py-0.2 rounded border ${badgeTheme.bg} ${badgeTheme.text} ${badgeTheme.border}`}
            >
              {session.averageQualityScore}分
            </span>
          </div>
          <p className="text-[10px] text-zinc-400 font-mono truncate">
            {session.traces.length} 次底层子查询 · 耗时 {latencyStr} · 引用 {session.citations.length} 处一手来源
          </p>
        </div>
      </div>

      <div className="flex items-center gap-1 text-[11px] text-indigo-400 font-mono shrink-0 pl-2">
        <span>展开审计</span>
        <Search className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" />
      </div>
    </button>
  );
};
