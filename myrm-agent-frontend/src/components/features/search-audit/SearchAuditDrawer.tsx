import React from 'react';
import {
  X,
  Search,
  Clock,
  HardDrive,
  ShieldCheck,
  ExternalLink,
  Layers,
  BarChart2,
  FileCheck2,
  AlertCircle,
  FileText,
} from 'lucide-react';
import { useSearchAuditStore, SearchAuditTab } from './useSearchAuditStore';
import {
  formatLatency,
  formatPayloadBytes,
  getScoreTierBadgeColor,
} from './searchAuditEngine';

export interface SearchAuditDrawerProps {
  className?: string;
}

export const SearchAuditDrawer: React.FC<SearchAuditDrawerProps> = ({
  className = '',
}) => {
  const {
    isDrawerOpen,
    activeSession,
    selectedCitation,
    activeTab,
    closeAuditDrawer,
    selectCitation,
    setActiveTab,
  } = useSearchAuditStore();

  if (!isDrawerOpen || !activeSession) {
    return null;
  }

  const { traces, citations, totalLatencyMs, totalPayloadBytes, averageQualityScore } =
    activeSession;

  const scoreBadge = getScoreTierBadgeColor(averageQualityScore);

  return (
    <aside
      data-testid="search-audit-drawer"
      aria-label="全透明检索链路审计看板"
      className={`fixed top-0 right-0 z-50 h-full w-full sm:w-[520px] bg-zinc-900/98 backdrop-blur-xl border-l border-zinc-800 shadow-2xl flex flex-col font-sans transition-all duration-300 ${className}`}
    >
      {/* 1. 抽屉顶部审计总览头 */}
      <header className="px-4 py-3 border-b border-zinc-800 bg-zinc-950/80 flex items-center justify-between">
        <div className="flex items-center gap-2 truncate">
          <div className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 shrink-0">
            <Search className="w-4 h-4" />
          </div>
          <div className="truncate">
            <div className="flex items-center gap-1.5">
              <h2 className="text-xs font-bold text-zinc-100">
                全透明检索链路审计
              </h2>
              <span
                className={`text-[10px] px-1.5 py-0.5 rounded border font-mono font-semibold flex items-center gap-1 ${scoreBadge.bg} ${scoreBadge.text} ${scoreBadge.border}`}
              >
                <span className={`w-1.5 h-1.5 rounded-full ${scoreBadge.dotColor}`} />
                {averageQualityScore} 分权威源
              </span>
            </div>
            <p className="text-[10px] text-zinc-400 truncate">
              拒绝黑盒摘要 · 真实链路耗时与 100 分量化打分
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={closeAuditDrawer}
          aria-label="关闭检索审计抽屉"
          title="关闭"
          className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors shrink-0"
        >
          <X className="w-4 h-4" />
        </button>
      </header>

      {/* 2. 统计卡片指标带 */}
      <div className="grid grid-cols-3 gap-2 p-3 bg-zinc-950/40 border-b border-zinc-850 text-xs">
        <div className="p-2 rounded-xl bg-zinc-900/80 border border-zinc-800 space-y-0.5">
          <div className="flex items-center gap-1 text-[10px] text-zinc-400 font-mono">
            <Clock className="w-3 h-3 text-indigo-400" />
            <span>网络总耗时</span>
          </div>
          <div className="font-bold text-zinc-200 font-mono">
            {formatLatency(totalLatencyMs)}
          </div>
        </div>

        <div className="p-2 rounded-xl bg-zinc-900/80 border border-zinc-800 space-y-0.5">
          <div className="flex items-center gap-1 text-[10px] text-zinc-400 font-mono">
            <HardDrive className="w-3 h-3 text-cyan-400" />
            <span>真实载荷大小</span>
          </div>
          <div className="font-bold text-zinc-200 font-mono">
            {formatPayloadBytes(totalPayloadBytes)}
          </div>
        </div>

        <div className="p-2 rounded-xl bg-zinc-900/80 border border-zinc-800 space-y-0.5">
          <div className="flex items-center gap-1 text-[10px] text-zinc-400 font-mono">
            <Layers className="w-3 h-3 text-emerald-400" />
            <span>子查询链路数</span>
          </div>
          <div className="font-bold text-zinc-200 font-mono">
            {traces.length} 次 API 调用
          </div>
        </div>
      </div>

      {/* 3. Tab 切换导航条 */}
      <nav className="flex items-center px-3 border-b border-zinc-800 bg-zinc-950/60 text-xs font-medium">
        <button
          type="button"
          onClick={() => {
            setActiveTab('waterfall');
          }}
          className={`flex items-center gap-1.5 py-2.5 px-3 border-b-2 transition-colors ${
            activeTab === 'waterfall'
              ? 'border-indigo-500 text-indigo-300 font-semibold'
              : 'border-transparent text-zinc-400 hover:text-zinc-200'
          }`}
        >
          <Clock className="w-3.5 h-3.5" />
          <span>耗时瀑布流 ({traces.length})</span>
        </button>

        <button
          type="button"
          onClick={() => {
            setActiveTab('quality_matrix');
          }}
          className={`flex items-center gap-1.5 py-2.5 px-3 border-b-2 transition-colors ${
            activeTab === 'quality_matrix'
              ? 'border-indigo-500 text-indigo-300 font-semibold'
              : 'border-transparent text-zinc-400 hover:text-zinc-200'
          }`}
        >
          <BarChart2 className="w-3.5 h-3.5" />
          <span>100分质量矩阵</span>
        </button>

        <button
          type="button"
          onClick={() => {
            setActiveTab('evidence_compare');
          }}
          className={`flex items-center gap-1.5 py-2.5 px-3 border-b-2 transition-colors ${
            activeTab === 'evidence_compare'
              ? 'border-indigo-500 text-indigo-300 font-semibold'
              : 'border-transparent text-zinc-400 hover:text-zinc-200'
          }`}
        >
          <FileCheck2 className="w-3.5 h-3.5" />
          <span>可信证据反查 ({citations.length})</span>
        </button>
      </nav>

      {/* 4. Tab 核心内容区 */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {/* Tab 1: 耗时瀑布流 */}
        {activeTab === 'waterfall' && (
          <div className="space-y-2.5">
            {traces.map((trace) => (
              <div
                key={trace.subQueryId}
                className="p-3 rounded-xl bg-zinc-950/80 border border-zinc-800 text-xs space-y-2"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="font-mono text-zinc-200 font-semibold flex items-center gap-1.5">
                    <span className="px-1.5 py-0.5 rounded bg-zinc-800 text-[10px] text-indigo-300 border border-zinc-700">
                      {trace.category.toUpperCase()}
                    </span>
                    <span className="truncate">{trace.queryText}</span>
                  </div>
                  <span className="font-mono text-indigo-400 font-bold shrink-0">
                    {formatLatency(trace.latencyMs)}
                  </span>
                </div>

                <div className="flex items-center justify-between text-[11px] text-zinc-400 pt-1 border-t border-zinc-850">
                  <span className="font-mono">
                    数据载荷: {formatPayloadBytes(trace.payloadBytes)}
                  </span>
                  <div className="flex items-center gap-2 font-mono text-[10px]">
                    <span
                      className={`px-1 rounded ${
                        trace.isFullText
                          ? 'bg-emerald-500/10 text-emerald-400'
                          : 'bg-zinc-800 text-zinc-400'
                      }`}
                    >
                      {trace.isFullText ? '正文全文' : '摘要切片'}
                    </span>
                    {trace.hasAiRewrite ? (
                      <span className="text-amber-400 flex items-center gap-0.5">
                        <AlertCircle className="w-3 h-3" />
                        存在二次改写
                      </span>
                    ) : (
                      <span className="text-emerald-400 flex items-center gap-0.5">
                        <ShieldCheck className="w-3 h-3" />
                        一手原文拉取
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Tab 2: 100分量化质量矩阵 */}
        {activeTab === 'quality_matrix' && (
          <div className="space-y-3">
            {citations.map((cite) => {
              const qm = cite.qualityMatrix;
              const tierBadge = getScoreTierBadgeColor(qm.compositeScore);
              return (
                <div
                  key={cite.id}
                  className="p-3.5 rounded-xl bg-zinc-950/80 border border-zinc-800 space-y-2.5 text-xs"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <h4 className="font-semibold text-zinc-100 truncate max-w-[280px]">
                        {cite.title}
                      </h4>
                      <p className="text-[10px] text-zinc-400 font-mono truncate">
                        {cite.domain} · {qm.tierLabel}
                      </p>
                    </div>
                    <span
                      className={`px-2 py-0.5 rounded-full font-mono font-bold text-xs border ${tierBadge.bg} ${tierBadge.text} ${tierBadge.border}`}
                    >
                      {qm.compositeScore} 分
                    </span>
                  </div>

                  {/* 四维量化评分条 */}
                  <div className="grid grid-cols-2 gap-2 text-[10px] font-mono bg-zinc-900/60 p-2 rounded-lg border border-zinc-850">
                    <div className="flex justify-between">
                      <span className="text-zinc-400">权威度 (40%):</span>
                      <span className="text-indigo-300 font-bold">{qm.authorityScore}分</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-400">一手性 (20%):</span>
                      <span className="text-emerald-300 font-bold">{qm.firstHandScore}分</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-400">信噪比 (20%):</span>
                      <span className="text-cyan-300 font-bold">{qm.signalToNoiseScore}分</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-400">时效性 (20%):</span>
                      <span className="text-amber-300 font-bold">{qm.freshnessScore}分</span>
                    </div>
                  </div>

                  <div className="flex items-center gap-1.5 text-[10px] text-zinc-400 font-mono">
                    <ShieldCheck className="w-3 h-3 text-indigo-400" />
                    <span>认证标识: {qm.verificationBadge}</span>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Tab 3: 可信证据反查 */}
        {activeTab === 'evidence_compare' && (
          <div className="space-y-3">
            <div className="flex items-center gap-1.5 overflow-x-auto pb-1">
              {citations.map((cite) => {
                const isSelected = selectedCitation?.id === cite.id;
                return (
                  <button
                    key={cite.id}
                    type="button"
                    onClick={() => {
                      selectCitation(cite);
                    }}
                    className={`px-2.5 py-1 rounded-lg text-xs font-mono whitespace-nowrap border transition-colors ${
                      isSelected
                        ? 'bg-indigo-600 text-white border-indigo-500'
                        : 'bg-zinc-950 text-zinc-400 border-zinc-800 hover:border-zinc-700'
                    }`}
                  >
                    {cite.domain}
                  </button>
                );
              })}
            </div>

            {selectedCitation && (
              <div className="p-3.5 rounded-xl bg-zinc-950/80 border border-zinc-800 space-y-3 text-xs">
                <div className="flex items-start justify-between gap-2">
                  <div className="space-y-0.5">
                    <h3 className="font-bold text-zinc-100">{selectedCitation.title}</h3>
                    <a
                      href={selectedCitation.url}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="text-[11px] text-indigo-400 hover:underline flex items-center gap-1 font-mono truncate"
                    >
                      <ExternalLink className="w-3 h-3 shrink-0" />
                      <span className="truncate">{selectedCitation.url}</span>
                    </a>
                  </div>
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-300 border border-zinc-700 shrink-0">
                    {selectedCitation.qualityMatrix.tierLabel}
                  </span>
                </div>

                {/* 提取摘要片段 */}
                <div className="space-y-1">
                  <div className="text-[10px] font-semibold text-zinc-400 font-mono">
                    模型回答引用的原始摘要:
                  </div>
                  <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800 text-zinc-300 leading-relaxed font-sans">
                    {selectedCitation.rawSnippet}
                  </div>
                </div>

                {/* 真实拉取的净菜全文片段 */}
                {selectedCitation.fullTextSnippet && (
                  <div className="space-y-1">
                    <div className="text-[10px] font-semibold text-emerald-400 font-mono flex items-center gap-1">
                      <FileText className="w-3 h-3" />
                      底层网络真实拉取的净菜全文片段:
                    </div>
                    <pre className="p-2.5 rounded-lg bg-zinc-900 border border-emerald-500/20 text-zinc-300 leading-relaxed font-mono whitespace-pre-wrap text-[11px] max-h-48 overflow-y-auto">
                      {selectedCitation.fullTextSnippet}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </aside>
  );
};
