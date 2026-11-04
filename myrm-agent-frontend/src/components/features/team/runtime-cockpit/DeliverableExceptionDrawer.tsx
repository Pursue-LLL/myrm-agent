import React, { useState } from 'react';
import {
  X,
  FileCheck2,
  AlertTriangle,
  CheckCircle2,
  AlertCircle,
  Clock,
  RefreshCw,
  FileText,
} from 'lucide-react';
import { useTeamRuntimeStore } from './useTeamRuntimeStore';

export const DeliverableExceptionDrawer: React.FC = () => {
  const {
    nodes,
    selectedNodeId,
    isDrawerOpen,
    closeDrawer,
    updateNodeDeliverable,
  } = useTeamRuntimeStore();

  const [editInput, setEditInput] = useState('');
  const node = nodes.find((n) => n.id === selectedNodeId);

  if (!isDrawerOpen || !node) {
    return null;
  }

  const deliverable = node.deliverable;
  const isStale = node.status === 'stale_prerequisite';

  const handleSimulateUpdate = () => {
    const newSummary = editInput || `${deliverable?.summary ?? '技术方案'}（经专家组重新优化修订）`;
    const newFact = `修订要点: 已重新测算资源开销，更新时间: ${new Date().toLocaleTimeString()}`;
    const baseFacts = deliverable?.decidedFacts ?? [];
    updateNodeDeliverable(node.id, newSummary, [...baseFacts, newFact]);
    setEditInput('');
  };

  return (
    <aside
      aria-label="交付物契约与例外检查抽屉"
      className="fixed inset-y-0 right-0 z-40 flex w-96 flex-col border-l border-slate-800 bg-slate-900/95 shadow-2xl backdrop-blur-md transition-all"
    >
      {/* Header */}
      <div className="flex h-14 shrink-0 items-center justify-between border-b border-slate-800 px-4">
        <div className="flex items-center space-x-2">
          <FileCheck2 className="h-5 w-5 text-blue-400" />
          <div>
            <h3 className="text-xs font-semibold text-slate-100">{node.label}</h3>
            <p className="text-[10px] text-slate-400">{node.assigneeAgentName}</p>
          </div>
        </div>
        <button
          type="button"
          onClick={closeDrawer}
          className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
          aria-label="关闭交付物抽屉"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* 前提失效告警条 */}
        {isStale && (
          <div className="rounded-lg border border-amber-500/40 bg-amber-950/20 p-3 text-xs text-amber-300">
            <div className="flex items-center space-x-1.5 font-semibold text-amber-400 mb-1">
              <AlertTriangle className="h-4 w-4" />
              <span>前提失效警示 (Stale Prerequisite)</span>
            </div>
            <p className="text-[11px] text-slate-300">{node.staleReason}</p>
          </div>
        )}

        {deliverable ? (
          <>
            {/* 成果摘要 */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-xs text-slate-400">
                <span className="font-semibold text-slate-200">交付物契约包</span>
                <span className="font-mono text-emerald-400">v{deliverable.version} 固化版本</span>
              </div>
              <div className="rounded-lg border border-slate-800 bg-slate-950/80 p-3 text-xs text-slate-300 leading-relaxed font-mono">
                {deliverable.summary}
              </div>
            </div>

            {/* 已决事实列表 */}
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-emerald-400 flex items-center space-x-1">
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  <span>已决事实列表 (Decided Facts)</span>
                </span>
                <span className="text-[10px] text-slate-400">{deliverable.decidedFacts.length} 项</span>
              </div>
              <div className="space-y-1.5">
                {deliverable.decidedFacts.map((fact) => (
                  <div
                    key={fact}
                    className="flex items-start space-x-2 rounded border border-emerald-500/20 bg-emerald-950/10 p-2 text-[11px] text-slate-200"
                  >
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 shrink-0 mt-0.5" />
                    <span>{fact}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* 未决风险与排除条款 */}
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-amber-400 flex items-center space-x-1">
                  <AlertCircle className="h-3.5 w-3.5" />
                  <span>未决风险与排除条款 (Exceptions)</span>
                </span>
                <span className="text-[10px] text-slate-400">
                  {deliverable.pendingRisksAndExceptions.length} 项
                </span>
              </div>
              <div className="space-y-1.5">
                {deliverable.pendingRisksAndExceptions.map((risk) => (
                  <div
                    key={risk}
                    className="flex items-start space-x-2 rounded border border-amber-500/20 bg-amber-950/10 p-2 text-[11px] text-slate-200"
                  >
                    <AlertCircle className="h-3.5 w-3.5 text-amber-400 shrink-0 mt-0.5" />
                    <span>{risk}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* 就地修订模拟触发器 */}
            <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3 text-xs space-y-2">
              <span className="text-[11px] font-semibold text-slate-300">
                修订上游交付物（测试反应式失效链路）:
              </span>
              <input
                type="text"
                placeholder="输入修订后方案摘要..."
                value={editInput}
                onChange={(e) => {
                  setEditInput(e.target.value);
                }}
                className="w-full rounded border border-slate-700 bg-slate-800 px-2.5 py-1.5 text-xs text-slate-100 placeholder-slate-500 focus:outline-none"
              />
              <button
                type="button"
                onClick={handleSimulateUpdate}
                className="inline-flex w-full items-center justify-center space-x-1.5 rounded bg-blue-600/80 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-500"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                <span>递增版本并广播下游前提失效</span>
              </button>
            </div>
          </>
        ) : (
          <div className="flex flex-col items-center justify-center p-8 text-center text-xs text-slate-400 space-y-2">
            <FileText className="h-8 w-8 text-slate-600" />
            <span>该节点交付物契约正在持续流式编排中...</span>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="flex h-11 shrink-0 items-center justify-between border-t border-slate-800 px-4 text-[10px] text-slate-400">
        <span className="flex items-center space-x-1">
          <Clock className="h-3 w-3" />
          <span>更新时间: {deliverable?.updatedAt ?? '刚刚'}</span>
        </span>
        <button
          type="button"
          onClick={closeDrawer}
          className="rounded px-2 py-1 text-slate-300 hover:bg-slate-800"
        >
          收起面板
        </button>
      </div>
    </aside>
  );
};
