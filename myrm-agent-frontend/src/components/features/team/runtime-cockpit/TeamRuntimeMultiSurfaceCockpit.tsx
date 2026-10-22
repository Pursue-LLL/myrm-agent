import React from 'react';
import {
  Users2,
  ShieldCheck,
  ShieldAlert,
  GitMerge,
  Sparkles,
} from 'lucide-react';
import { useTeamRuntimeStore } from './useTeamRuntimeStore';
import { TeamDependencyCanvas } from './TeamDependencyCanvas';
import { CoordinationReductionCard } from './CoordinationReductionCard';
import { ConflictResolutionModal } from './ConflictResolutionModal';
import { DeliverableExceptionDrawer } from './DeliverableExceptionDrawer';

export const TeamRuntimeMultiSurfaceCockpit: React.FC = () => {
  const {
    teamName,
    nodes,
    conflicts,
    openConflictModal,
  } = useTeamRuntimeStore();

  const pendingConflicts = conflicts.filter((c) => c.status === 'pending_arbitration');
  const completedNodesCount = nodes.filter((n) => n.status === 'completed').length;
  const staleNodesCount = nodes.filter((n) => n.status === 'stale_prerequisite').length;

  return (
    <section
      aria-label="数字团队运行驾驶舱"
      className="relative flex min-h-screen w-full flex-col bg-slate-950 text-slate-100"
    >
      {/* 顶部团队作战全景指挥条 */}
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-slate-800 bg-slate-900/90 px-6 backdrop-blur-md">
        <div className="flex items-center space-x-3">
          <div className="rounded-lg bg-blue-500/10 p-2 text-blue-400">
            <Users2 className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h2 className="text-sm font-semibold text-slate-100">{teamName}</h2>
              <span className="rounded-full bg-blue-500/20 px-2 py-0.5 text-[10px] font-medium text-blue-300">
                Team Runtime Cockpit
              </span>
            </div>
            <p className="text-[11px] text-slate-400">
              多智能体协同分工 · DAG 反应式依赖拓扑 · 拒绝隐形第四人线下对齐
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          {staleNodesCount > 0 && (
            <div className="flex items-center space-x-1.5 rounded-full bg-amber-500/10 border border-amber-500/30 px-2.5 py-1 text-[11px] text-amber-300">
              <span className="h-2 w-2 rounded-full bg-amber-400 animate-pulse" />
              <span>{staleNodesCount} 个节点前提失效已自动拦截</span>
            </div>
          )}

          {pendingConflicts.length > 0 ? (
            <button
              type="button"
              onClick={() => {
                openConflictModal(pendingConflicts[0].id);
              }}
              className="inline-flex items-center space-x-1.5 rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-medium text-white shadow hover:bg-amber-500 animate-pulse"
            >
              <ShieldAlert className="h-4 w-4" />
              <span>待仲裁矛盾 ({pendingConflicts.length})</span>
            </button>
          ) : (
            <div className="inline-flex items-center space-x-1 rounded-full bg-emerald-500/10 px-2.5 py-1 text-[11px] text-emerald-400">
              <ShieldCheck className="h-3.5 w-3.5" />
              <span>所有节点契约对齐，无业务死锁</span>
            </div>
          )}
        </div>
      </header>

      {/* 主体作战大屏 */}
      <main className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* 全局协同指标概览 */}
        <div className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/60 px-4 py-2 text-xs text-slate-400">
          <div className="flex items-center space-x-4">
            <span className="flex items-center space-x-1">
              <GitMerge className="h-3.5 w-3.5 text-blue-400" />
              <span>DAG 总节点数: <strong className="text-slate-200">{nodes.length}</strong></span>
            </span>
            <span>已交付契约: <strong className="text-emerald-400">{completedNodesCount}</strong></span>
            <span>失效重定中: <strong className="text-amber-400">{staleNodesCount}</strong></span>
          </div>

          <div className="flex items-center space-x-1 text-slate-400">
            <Sparkles className="h-3 w-3 text-purple-400" />
            <span>智能反应式失效广播与仲裁闭环已就绪</span>
          </div>
        </div>

        {/* 反应式 DAG 依赖拓扑画布 */}
        <TeamDependencyCanvas />

        {/* 协同减负度量大盘 */}
        <CoordinationReductionCard />
      </main>

      {/* 模态与右侧抽屉 */}
      <ConflictResolutionModal />
      <DeliverableExceptionDrawer />
    </section>
  );
};
