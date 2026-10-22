/**
 * [INPUT]: EventCausalityLineageDeckProps with lineages list, selection state, and reverse-lookup callback.
 * [OUTPUT]: Interactive Event-Driven Causality Lineage Deck with DAG breadcrumbs and reverse file attribution.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/EventCausalityLineageDeck.tsx
 */

import React, { useState, useMemo } from 'react';
import {
  CausalityLineageRecordItem,
  EventCausalityLineageDeckProps,
  FileAttributionResultItem,
} from './eventCausalityLineageTypes';

function getSourceBadgeColor(sourceType: string): string {
  switch (sourceType) {
    case 'github_webhook':
      return 'bg-purple-900/60 text-purple-300 border-purple-700/60';
    case 'slack_mention':
      return 'bg-emerald-900/60 text-emerald-300 border-emerald-700/60';
    case 'mcp_event':
      return 'bg-cyan-900/60 text-cyan-300 border-cyan-700/60';
    case 'cron':
      return 'bg-amber-900/60 text-amber-300 border-amber-700/60';
    default:
      return 'bg-slate-800 text-slate-300 border-slate-700';
  }
}

function getChangeBadgeColor(changeType: string): string {
  switch (changeType) {
    case 'created':
      return 'bg-emerald-950 text-emerald-400 border-emerald-800';
    case 'deleted':
      return 'bg-rose-950 text-rose-400 border-rose-800';
    default:
      return 'bg-sky-950 text-sky-400 border-sky-800';
  }
}

export const EventCausalityLineageDeck: React.FC<EventCausalityLineageDeckProps> = ({
  lineages,
  selectedTraceId,
  onSelectTrace,
  onReverseLookupFile,
  onRefresh,
  isRefreshing = false,
}) => {
  const [internalSelectedId, setInternalSelectedId] = useState<string>(
    selectedTraceId || (lineages.length > 0 ? lineages[0].causality_trace_id : '')
  );
  const [searchFilePath, setSearchFilePath] = useState<string>('');
  const [reverseResults, setReverseResults] = useState<FileAttributionResultItem[] | null>(null);
  const [isSearching, setIsSearching] = useState<boolean>(false);

  const activeTraceId = selectedTraceId || internalSelectedId;

  const currentTrace = useMemo(() => {
    return lineages.find((l) => l.causality_trace_id === activeTraceId) || lineages[0] || null;
  }, [lineages, activeTraceId]);

  const handleSelect = (traceId: string) => {
    setInternalSelectedId(traceId);
    setReverseResults(null);
    if (onSelectTrace) {
      onSelectTrace(traceId);
    }
  };

  const handleSearchReverse = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchFilePath.trim() || !onReverseLookupFile) return;

    setIsSearching(true);
    try {
      const res = await onReverseLookupFile(searchFilePath.trim());
      setReverseResults(res);
    } finally {
      setIsSearching(false);
    }
  };

  const clearSearch = () => {
    setSearchFilePath('');
    setReverseResults(null);
  };

  return (
    <div className="flex flex-col h-full bg-slate-950 text-slate-100 rounded-xl border border-slate-800 overflow-hidden shadow-2xl">
      {/* Top Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 border-b border-slate-800 bg-slate-900/80">
        <div>
          <h2 className="text-lg font-bold tracking-tight text-white flex items-center gap-2">
            <span className="text-amber-400">⚡</span> 事件驱动因果溯源与动作归因图谱
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            从外部事件触发、规则评估、决策思考到最终代码变更全链路因果 DAG 与秒级反向文件归因
          </p>
        </div>

        {/* Reverse lookup search input & Refresh */}
        <div className="flex items-center gap-2">
          <form onSubmit={handleSearchReverse} className="flex items-center gap-1.5">
            <input
              type="text"
              placeholder="输入文件路径反查因果..."
              value={searchFilePath}
              onChange={(e) => setSearchFilePath(e.target.value)}
              className="px-3 py-1.5 text-xs bg-slate-800 border border-slate-700 rounded-lg text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-amber-500 w-52 sm:w-64"
            />
            <button
              type="submit"
              disabled={isSearching || !searchFilePath.trim()}
              className="px-3 py-1.5 text-xs font-medium rounded-lg bg-amber-500/20 text-amber-300 border border-amber-500/40 hover:bg-amber-500/30 disabled:opacity-50 transition-colors"
            >
              {isSearching ? '反查中...' : '反向归因'}
            </button>
            {reverseResults && (
              <button
                type="button"
                onClick={clearSearch}
                className="px-2 py-1.5 text-xs text-slate-400 hover:text-slate-200"
              >
                清除
              </button>
            )}
          </form>

          {onRefresh && (
            <button
              onClick={onRefresh}
              disabled={isRefreshing}
              className="p-1.5 text-xs bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg text-slate-300 transition-colors"
              title="刷新链路"
            >
              🔄
            </button>
          )}
        </div>
      </div>

      {/* Main Grid: Left List + Right Detail/Reverse */}
      <div className="grid grid-cols-1 lg:grid-cols-12 flex-1 min-h-0 divide-y lg:divide-y-0 lg:divide-x divide-slate-800">
        {/* Left Column: Trace Lineage Index */}
        <div className="lg:col-span-4 flex flex-col min-h-0 overflow-y-auto p-3 space-y-2 bg-slate-900/30">
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-400 px-2 py-1">
            已捕获因果链 ({lineages.length})
          </div>

          {lineages.length === 0 ? (
            <div className="text-center py-10 text-xs text-slate-500">
              暂无已记录的事件因果链路
            </div>
          ) : (
            lineages.map((lineage) => {
              const isSelected = lineage.causality_trace_id === currentTrace?.causality_trace_id && !reverseResults;
              return (
                <div
                  key={lineage.causality_trace_id}
                  onClick={() => handleSelect(lineage.causality_trace_id)}
                  className={`p-3 rounded-xl border text-xs cursor-pointer transition-all ${
                    isSelected
                      ? 'bg-amber-950/20 border-amber-500/50 shadow-md shadow-amber-950/20 ring-1 ring-amber-500/30'
                      : 'bg-slate-900/60 border-slate-800/80 hover:bg-slate-850 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-center justify-between gap-1.5 mb-1.5">
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-mono border ${getSourceBadgeColor(
                        lineage.trigger.source_type
                      )}`}
                    >
                      {lineage.trigger.source_type}
                    </span>
                    <span className="text-[10px] text-slate-500 font-mono">
                      {lineage.causality_trace_id}
                    </span>
                  </div>

                  <div className="font-medium text-slate-200 line-clamp-1 mb-1">
                    {lineage.trigger.event_name}
                  </div>
                  <div className="text-[11px] text-slate-400 line-clamp-1 mb-2">
                    {lineage.trigger.payload_summary}
                  </div>

                  <div className="flex items-center justify-between text-[10px] text-slate-400 pt-1.5 border-t border-slate-800/60 font-mono">
                    <span>规则: {lineage.rule.rule_id}</span>
                    <span className="text-amber-400/80">
                      {lineage.artifacts.length} 个文件 · {lineage.total_tokens} tok
                    </span>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Right Column: Reverse Lookup View OR Full Causality DAG View */}
        <div className="lg:col-span-8 flex flex-col min-h-0 overflow-y-auto p-4 space-y-4 bg-slate-950">
          {reverseResults !== null ? (
            /* Reverse Lookup Search View */
            <div className="space-y-4">
              <div className="flex items-center justify-between p-3 rounded-xl bg-amber-950/30 border border-amber-600/40">
                <div className="flex items-center gap-2">
                  <span className="text-base text-amber-400">🔍</span>
                  <div>
                    <div className="text-xs font-semibold text-amber-200">
                      文件倒排反向归因结果：{searchFilePath}
                    </div>
                    <div className="text-[11px] text-amber-300/80">
                      命中 {reverseResults.length} 次由外部事件驱动的变更记录
                    </div>
                  </div>
                </div>
                <button
                  onClick={clearSearch}
                  className="px-2.5 py-1 text-xs bg-slate-800 hover:bg-slate-700 rounded-md text-slate-300"
                >
                  返回主链路
                </button>
              </div>

              {reverseResults.length === 0 ? (
                <div className="p-8 text-center text-xs text-slate-500 bg-slate-900/40 rounded-xl border border-slate-800">
                  未检索到针对目标路径的事件驱动修改记录。
                </div>
              ) : (
                reverseResults.map((attr, idx) => (
                  <div
                    key={`${attr.causality_trace_id}-${idx}`}
                    className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-2.5 text-xs"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className={`px-2 py-0.5 rounded text-[10px] border ${getSourceBadgeColor(attr.source_type)}`}>
                          {attr.source_type}
                        </span>
                        <span className="font-semibold text-slate-200">
                          {attr.event_name} ({attr.trigger_event_id})
                        </span>
                      </div>
                      <span className="text-slate-500 font-mono text-[10px]">
                        Trace: {attr.causality_trace_id}
                      </span>
                    </div>

                    <div className="p-2.5 rounded-lg bg-slate-950/80 border border-slate-800/80">
                      <div className="text-[11px] text-amber-300 font-medium mb-1">
                        智能体角色 [{attr.agent_role}] 决策依据：
                      </div>
                      <div className="text-slate-300 italic">{attr.rationale}</div>
                    </div>

                    <div className="flex items-center justify-between pt-1 text-[11px]">
                      <div className="flex items-center gap-2">
                        <span className={`px-1.5 py-0.5 rounded text-[10px] border ${getChangeBadgeColor(attr.change_record.change_type)}`}>
                          {attr.change_record.change_type}
                        </span>
                        <code className="text-slate-300 font-mono">{attr.change_record.file_path}</code>
                      </div>
                      <span className="text-slate-500 font-mono text-[10px]">
                        Commit: {attr.change_record.commit_sha || 'local_uncommitted'}
                      </span>
                    </div>
                    <div className="text-[11px] font-mono text-emerald-400/90 bg-emerald-950/30 p-2 rounded border border-emerald-900/50">
                      {attr.change_record.diff_summary}
                    </div>
                  </div>
                ))
              )}
            </div>
          ) : currentTrace ? (
            /* Causality DAG View */
            <div className="space-y-4">
              {/* Topology Breadcrumb */}
              <div className="p-3 rounded-xl bg-slate-900/80 border border-slate-800 flex flex-wrap items-center gap-2 text-xs">
                <span className="text-slate-400 font-medium">因果链拓扑:</span>
                <span className="px-2 py-0.5 rounded bg-purple-950/80 border border-purple-800 text-purple-300 text-[11px]">
                  ⚡ {currentTrace.trigger.source_type}
                </span>
                <span className="text-slate-600">➔</span>
                <span className="px-2 py-0.5 rounded bg-blue-950/80 border border-blue-800 text-blue-300 text-[11px]">
                  📜 {currentTrace.rule.rule_id}
                </span>
                <span className="text-slate-600">➔</span>
                <span className="px-2 py-0.5 rounded bg-amber-950/80 border border-amber-800 text-amber-300 text-[11px]">
                  🧠 {currentTrace.actions.length} 动作步
                </span>
                <span className="text-slate-600">➔</span>
                <span className="px-2 py-0.5 rounded bg-emerald-950/80 border border-emerald-800 text-emerald-300 text-[11px]">
                  📁 {currentTrace.artifacts.length} 产物
                </span>
              </div>

              {/* Node 1: Trigger & Rule Card */}
              <div className="p-4 rounded-xl bg-slate-900/50 border border-slate-800 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                    <span className="text-purple-400">⚡</span> 诱发外部事件与自动化规则
                  </span>
                  <span className="text-[10px] text-slate-500 font-mono">
                    Event ID: {currentTrace.trigger.event_id}
                  </span>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                  <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80 space-y-1">
                    <div className="text-[11px] text-slate-400">事件类型</div>
                    <div className="font-semibold text-purple-300">{currentTrace.trigger.event_name}</div>
                    <div className="text-[11px] text-slate-300 mt-1">{currentTrace.trigger.payload_summary}</div>
                  </div>
                  <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80 space-y-1">
                    <div className="text-[11px] text-slate-400">匹配规则</div>
                    <div className="font-semibold text-blue-300">{currentTrace.rule.rule_name}</div>
                    <code className="block text-[10px] text-blue-200/80 font-mono bg-blue-950/40 p-1 rounded mt-1">
                      {currentTrace.rule.matched_condition}
                    </code>
                  </div>
                </div>
              </div>

              {/* Node 2: Cognitive Action Steps */}
              <div className="p-4 rounded-xl bg-slate-900/50 border border-slate-800 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                    <span className="text-amber-400">🧠</span> 认知决策与执行动作流
                  </span>
                  <span className="text-[10px] text-slate-400 font-mono">
                    主角色: {currentTrace.agent_role} · 耗时 {currentTrace.total_duration_ms.toFixed(1)}ms
                  </span>
                </div>

                <div className="space-y-2.5">
                  {currentTrace.actions.length === 0 ? (
                    <div className="text-xs text-slate-500 py-3 text-center">无独立动作步骤</div>
                  ) : (
                    currentTrace.actions.map((act, index) => (
                      <div
                        key={act.action_id}
                        className="p-3 rounded-lg bg-slate-950/70 border border-slate-800 space-y-1.5 text-xs"
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span className="w-5 h-5 rounded-full bg-amber-500/20 text-amber-400 flex items-center justify-center font-bold text-[10px]">
                              {index + 1}
                            </span>
                            <span className="font-semibold text-slate-200">{act.agent_role}</span>
                            <code className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-cyan-300 font-mono">
                              {act.tool_name}
                            </code>
                          </div>
                          <span className="text-[10px] text-slate-400 font-mono">
                            {act.duration_ms.toFixed(1)}ms · {act.tokens_consumed} tok
                          </span>
                        </div>
                        <div className="text-[11px] text-slate-300 pl-7">
                          <span className="text-amber-400/90 font-medium">决策理由: </span>
                          {act.decision_rationale}
                        </div>
                        {act.input_summary && (
                          <div className="text-[10px] text-slate-500 font-mono pl-7 truncate">
                            参数: {act.input_summary}
                          </div>
                        )}
                      </div>
                    ))
                  )}
                </div>
              </div>

              {/* Node 3: Artifact Changes */}
              <div className="p-4 rounded-xl bg-slate-900/50 border border-slate-800 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                    <span className="text-emerald-400">📁</span> 产物变更归因
                  </span>
                  <span className="text-[10px] text-slate-400 font-mono">
                    共 {currentTrace.artifacts.length} 处文件变动
                  </span>
                </div>

                <div className="space-y-2">
                  {currentTrace.artifacts.length === 0 ? (
                    <div className="text-xs text-slate-500 py-3 text-center">无文件修改记录</div>
                  ) : (
                    currentTrace.artifacts.map((art) => (
                      <div
                        key={art.file_path}
                        className="p-3 rounded-lg bg-slate-950/70 border border-slate-800 space-y-1.5 text-xs"
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span
                              className={`px-1.5 py-0.5 rounded text-[10px] border ${getChangeBadgeColor(
                                art.change_type
                              )}`}
                            >
                              {art.change_type}
                            </span>
                            <code className="text-slate-200 font-mono text-xs">{art.file_path}</code>
                          </div>
                          {art.commit_sha && (
                            <span className="text-[10px] text-slate-500 font-mono">
                              Commit: {art.commit_sha.slice(0, 7)}
                            </span>
                          )}
                        </div>
                        <div className="text-[11px] font-mono text-emerald-300/90 bg-emerald-950/20 p-2 rounded border border-emerald-900/30">
                          {art.diff_summary}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="text-center py-20 text-xs text-slate-500">
              请从左侧选择一条因果链查看详细拓扑
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
