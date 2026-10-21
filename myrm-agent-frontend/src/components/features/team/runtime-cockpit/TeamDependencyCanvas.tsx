import React from 'react';
import {
  CheckCircle2,
  Loader2,
  AlertTriangle,
  Clock,
  Layers,
  ShieldAlert,
  ArrowRight,
  GitBranch,
} from 'lucide-react';
import { useTeamRuntimeStore } from './useTeamRuntimeStore';
import type { DAGNode, DAGNodeStatus } from './teamRuntimeTypes';

export const TeamDependencyCanvas: React.FC = () => {
  const {
    nodes,
    conflicts,
    selectedNodeId,
    selectNode,
    openConflictModal,
  } = useTeamRuntimeStore();

  const pendingConflict = conflicts.find((c) => c.status === 'pending_arbitration');

  const getStatusBadge = (status: DAGNodeStatus) => {
    if (status === 'completed') {
      return (
        <span className="inline-flex items-center space-x-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-400">
          <CheckCircle2 className="h-3 w-3" />
          <span>已交付</span>
        </span>
      );
    }
    if (status === 'running') {
      return (
        <span className="inline-flex items-center space-x-1 rounded-full bg-blue-500/10 px-2 py-0.5 text-[10px] font-medium text-blue-400">
          <Loader2 className="h-3 w-3 animate-spin" />
          <span>推进中</span>
        </span>
      );
    }
    if (status === 'stale_prerequisite') {
      return (
        <span className="inline-flex items-center space-x-1 rounded-full bg-amber-500/20 px-2 py-0.5 text-[10px] font-medium text-amber-300 animate-pulse">
          <AlertTriangle className="h-3 w-3 text-amber-400" />
          <span>前提已失效</span>
        </span>
      );
    }
    return (
      <span className="inline-flex items-center space-x-1 rounded-full bg-slate-800 px-2 py-0.5 text-[10px] font-medium text-slate-400">
        <Clock className="h-3 w-3" />
        <span>等待前置</span>
      </span>
    );
  };

  return (
    <div className="relative flex flex-col rounded-xl border border-slate-800 bg-slate-900/80 p-4 shadow-xl backdrop-blur-md">
      <div className="flex items-center justify-between border-b border-slate-800 pb-3">
        <div className="flex items-center space-x-2">
          <GitBranch className="h-4 w-4 text-sky-400" />
          <h3 className="text-xs font-semibold text-slate-100">
            团队 DAG 反应式依赖拓扑画布
          </h3>
          <span className="rounded bg-sky-500/10 px-1.5 py-0.5 text-[10px] font-medium text-sky-400">
            Reactive Topology
          </span>
        </div>

        {pendingConflict && (
          <button
            type="button"
            onClick={() => {
              openConflictModal(pendingConflict.id);
            }}
            className="inline-flex items-center space-x-1.5 rounded-full border border-amber-500/40 bg-amber-950/40 px-3 py-1 text-[11px] font-medium text-amber-300 hover:bg-amber-900/40 animate-pulse"
            aria-label="查看业务冲突仲裁卡片"
          >
            <ShieldAlert className="h-3.5 w-3.5 text-amber-400" />
            <span>检测到不可调和矛盾：点击人类拍板</span>
          </button>
        )}
      </div>

      {/* DAG 节点反应式拓扑流 */}
      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-5">
        {nodes.map((node, index) => {
          const isSelected = selectedNodeId === node.id;
          const isStale = node.status === 'stale_prerequisite';

          return (
            <div key={node.id} className="relative flex flex-col">
              <button
                type="button"
                onClick={() => {
                  selectNode(node.id);
                }}
                className={`flex flex-col justify-between rounded-lg border p-3 text-left transition-all ${
                  isSelected
                    ? 'border-blue-500 bg-blue-950/30 shadow-[0_0_12px_rgba(59,130,246,0.2)]'
                    : isStale
                    ? 'border-amber-500/80 bg-amber-950/20 shadow-[0_0_12px_rgba(245,158,11,0.25)]'
                    : 'border-slate-800 bg-slate-850/70 hover:border-slate-700 hover:bg-slate-800/60'
                }`}
              >
                <div>
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[10px] text-slate-500">
                      STEP 0{index + 1}
                    </span>
                    {getStatusBadge(node.status)}
                  </div>

                  <h4 className="mt-2 text-xs font-semibold text-slate-200">
                    {node.label}
                  </h4>
                  <p className="mt-0.5 text-[11px] text-slate-400">{node.assigneeAgentName}</p>
                </div>

                <div className="mt-3 border-t border-slate-800/80 pt-2 text-[10px] text-slate-400">
                  {node.deliverable ? (
                    <div className="flex items-center justify-between text-slate-300">
                      <span className="font-mono text-emerald-400">
                        v{node.deliverable.version} 契约就绪
                      </span>
                      <span>{node.deliverable.decidedFacts.length} 条已决事实</span>
                    </div>
                  ) : (
                    <span>产出编排中...</span>
                  )}
                </div>

                {isStale && node.staleReason && (
                  <div className="mt-2 rounded bg-amber-950/40 p-1.5 text-[10px] text-amber-300 border border-amber-800/60">
                    {node.staleReason}
                  </div>
                )}
              </button>

              {index < nodes.length - 1 && (
                <div className="hidden sm:flex absolute -right-2.5 top-1/2 -translate-y-1/2 z-10 text-slate-600">
                  <ArrowRight className="h-4 w-4" />
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="mt-3 flex items-center justify-between text-[11px] text-slate-400 border-t border-slate-800/80 pt-2.5">
        <span className="flex items-center space-x-1">
          <Layers className="h-3 w-3 text-slate-400" />
          <span>点击任意节点可展开右侧交付物契约、已决事实与未决例外清单</span>
        </span>
        <span className="font-mono text-slate-400">
          全拓扑节点数: {nodes.length} · 冲突仲裁项: {conflicts.length}
        </span>
      </div>
    </div>
  );
};
