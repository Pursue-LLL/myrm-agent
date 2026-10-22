import React from 'react';
import {
  CheckCircle2,
  Clock,
  Loader2,
  ArrowRight,
  Search,
  BarChart3,
  PenTool,
  GitFork,
  FileCheck,
} from 'lucide-react';
import { useMultiRoleRelayStore } from './useMultiRoleRelayStore';
import { AgentRoleType, RelayStage } from './multiRoleRelayTypes';
import { calculateRelayProgress } from './relayPipelineEngine';

export const MultiRoleRelayStepTimeline: React.FC = () => {
  const {
    stages,
    activeStageId,
    selectedSnapshot,
    selectStageSnapshot,
    advancePipeline,
  } = useMultiRoleRelayStore();

  const progress = calculateRelayProgress(stages);

  const getRoleIcon = (role: AgentRoleType) => {
    switch (role) {
      case 'researcher':
        return <Search className="w-3.5 h-3.5 text-sky-400" />;
      case 'analyst':
        return <BarChart3 className="w-3.5 h-3.5 text-indigo-400" />;
      case 'copywriter':
      case 'reviewer':
      case 'engineer':
      default:
        return <PenTool className="w-3.5 h-3.5 text-amber-400" />;
    }
  };

  const getStatusBadge = (stage: RelayStage) => {
    switch (stage.status) {
      case 'completed':
        return (
          <span className="flex items-center space-x-1 text-[10px] text-emerald-400 font-medium">
            <CheckCircle2 className="w-3 h-3" />
            <span>完成</span>
          </span>
        );
      case 'in_progress':
        return (
          <span className="flex items-center space-x-1 text-[10px] text-amber-400 font-medium animate-pulse">
            <Loader2 className="w-3 h-3 animate-spin" />
            <span>进行中</span>
          </span>
        );
      case 'pending':
      default:
        return (
          <span className="flex items-center space-x-1 text-[10px] text-slate-500 font-medium">
            <Clock className="w-3 h-3" />
            <span>排队中</span>
          </span>
        );
    }
  };

  return (
    <nav
      aria-label="多角色接力阶段阶梯进度条"
      className="w-full bg-slate-950/90 border-b border-slate-800 p-3 flex flex-col space-y-2.5 text-slate-100"
      data-testid="multi-role-relay-step-timeline"
    >
      {/* 头部标题与总体进度 */}
      <div className="flex items-center justify-between text-xs">
        <div className="flex items-center space-x-2">
          <div className="p-1 rounded bg-indigo-600/20 text-indigo-400 border border-indigo-500/30">
            <FileCheck className="w-3.5 h-3.5" />
          </div>
          <span className="font-bold text-white tracking-tight">
            多智能体接力流水线
          </span>
          <span className="text-[10px] text-slate-400">
            {progress.completed}/{progress.total} 棒已交接 ({progress.progressPercent}%)
          </span>
        </div>

        <button
          type="button"
          onClick={() => advancePipeline()}
          aria-label="推进至下一棒角色"
          className="text-[10px] px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition-colors"
        >
          模拟推进下一棒
        </button>
      </div>

      {/* 阶梯时序胶囊条 (Relay Step Capsules) */}
      <div className="flex items-center space-x-2 overflow-x-auto scrollbar-none py-1">
        {stages.map((stage, idx) => {
          const isSelected = selectedSnapshot?.stageId === stage.id;
          const isActive = stage.id === activeStageId;

          return (
            <React.Fragment key={stage.id}>
              <button
                type="button"
                onClick={() => {
                  if (stage.snapshot) {
                    selectStageSnapshot(stage.id);
                  }
                }}
                disabled={!stage.snapshot}
                aria-label={`查看第 ${stage.stepNumber} 棒 ${stage.roleName} 的交接产物`}
                className={`flex items-center space-x-2 px-3 py-1.5 rounded-lg border text-xs transition-all shrink-0 ${
                  isSelected
                    ? 'bg-indigo-950/80 border-indigo-500 text-white shadow-md ring-1 ring-indigo-500/50'
                    : isActive
                    ? 'bg-slate-900 border-amber-500/60 text-slate-200'
                    : 'bg-slate-900/60 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200'
                } ${!stage.snapshot ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer'}`}
              >
                <div className="p-1 rounded-md bg-slate-800/80">
                  {getRoleIcon(stage.role)}
                </div>
                <div className="text-left">
                  <div className="flex items-center space-x-1.5">
                    <span className="font-semibold text-[11px] text-slate-200">
                      {stage.stepNumber}. {stage.roleName}
                    </span>
                    {getStatusBadge(stage)}
                  </div>
                  <div className="text-[10px] text-slate-400 truncate max-w-[140px]">
                    {stage.snapshot ? stage.snapshot.artifactName : stage.actionSummary}
                  </div>
                </div>

                {stage.snapshot && stage.snapshot.version > 1 && (
                  <span
                    className="p-1 rounded bg-amber-950 text-amber-300 border border-amber-800/60"
                    title="包含用户发起的 Fork 分支修改"
                  >
                    <GitFork className="w-2.5 h-2.5" />
                  </span>
                )}
              </button>

              {idx < stages.length - 1 && (
                <ArrowRight className="w-3.5 h-3.5 text-slate-600 shrink-0" />
              )}
            </React.Fragment>
          );
        })}
      </div>
    </nav>
  );
};
