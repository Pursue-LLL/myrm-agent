import React from 'react';
import {
  GitCommit,
  Plus,
  RotateCcw,
  Network,
  Activity,
  Layers,
} from 'lucide-react';
import { useCommGraphStore } from './useCommGraphStore';
import { CommGraphEmptyStateCard } from './CommGraphEmptyStateCard';
import { CommGraphTimelineTrack } from './CommGraphTimelineTrack';

export const CommGraphMultiSurfaceCard: React.FC = () => {
  const {
    events,
    isLive,
    isPipelineInitializing,
    addCommEvent,
    clearEvents,
    setPipelineInitializing,
  } = useCommGraphStore();

  const handleSimulateNextStep = () => {
    const nextStep = events.length + 1;
    const agentRoles = [
      'CoordinatorAgent (协调总管)',
      'ArchitectAgent (架构师)',
      'CoderAgent (全栈工程师)',
      'ReviewerAgent (代码审计员)',
      'DeployerAgent (发布专家)',
    ];

    const fromIdx = (nextStep - 1) % (agentRoles.length - 1);
    const toIdx = fromIdx + 1;

    addCommEvent({
      stepIndex: nextStep,
      fromAgent: agentRoles[fromIdx],
      toAgent: agentRoles[toIdx],
      action: `dispatch_pipeline_stage_${nextStep}`,
      payloadSummary: `流转协同上下文数据包: 阶段 #${nextStep} 已完成校验并向下一跳 Agent 投递任务输入`,
      status: 'completed',
      latencyMs: Math.floor(20 + Math.random() * 40),
    });
  };

  return (
    <div className="w-full max-w-4xl mx-auto rounded-xl border border-slate-800 bg-slate-900/90 p-5 text-slate-100 shadow-xl backdrop-blur-md">
      {/* 头部元信息与操作栏 */}
      <div className="flex flex-col gap-3 pb-4 border-b border-slate-800 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
            <Network className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold text-white tracking-tight">
                多智能体协同通讯图 (Comm-Graph)
              </h2>
              {events.length > 0 && isLive && (
                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-400 border border-emerald-500/20">
                  <Activity className="h-3 w-3 text-emerald-400" />
                  Live 实时链路
                </span>
              )}
            </div>
            <p className="mt-0.5 text-xs text-slate-400">
              清晰空状态引导 • 实时/历史双向游标记忆防丢失
            </p>
          </div>
        </div>

        {/* 顶部操作区 */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleSimulateNextStep}
            className="inline-flex items-center gap-1.5 rounded-lg border border-indigo-500/30 bg-indigo-600/20 px-3 py-1.5 text-xs font-semibold text-indigo-300 hover:bg-indigo-600/30 active:scale-95 transition-all focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <Plus className="h-3.5 w-3.5" />
            注入协同事件
          </button>

          <button
            type="button"
            onClick={() => {
              clearEvents();
              setPipelineInitializing(true);
            }}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800/80 px-2.5 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-700 active:scale-95 transition-all focus:outline-none focus:ring-2 focus:ring-slate-500"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            清空重置
          </button>
        </div>
      </div>

      {/* 主视图分流渲染：空状态 vs 时间轴 */}
      <div className="mt-4">
        {events.length === 0 ? (
          <CommGraphEmptyStateCard />
        ) : (
          <CommGraphTimelineTrack />
        )}
      </div>

      {/* 底部架构说明与指标摘要 */}
      <div className="mt-4 flex flex-col gap-2 pt-3 border-t border-slate-800/80 text-[11px] text-slate-400 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <Layers className="h-3.5 w-3.5 text-indigo-400" />
          <span>协同流水线拓扑: 5 节点有向无环图 (DAG)</span>
        </div>
        <div className="flex items-center gap-3">
          <span>
            流水线状态:{' '}
            <strong className="text-slate-300">
              {isPipelineInitializing ? '初始化中' : '正常通讯中'}
            </strong>
          </span>
          <span>•</span>
          <span data-testid="recorded-events-count">
            已记录事件: {events.length}
          </span>
        </div>
      </div>
    </div>
  );
};
