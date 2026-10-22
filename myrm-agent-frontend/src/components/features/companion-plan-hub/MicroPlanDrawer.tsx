/**
 * MicroPlanDrawer.tsx
 * 毛玻璃半透明轻量迷你工作台抽屉：结构化任务计划书展示、子任务跳过微调与确认开工
 */

import React from 'react';
import {
  Bot,
  CheckCircle2,
  Clock,
  Edit3,
  Play,
  SkipForward,
  Sparkles,
  X,
} from 'lucide-react';
import { calculatePlanProgress } from './companionPlanHubEngine';
import { useCompanionPlanHubStore } from './useCompanionPlanHubStore';

export interface MicroPlanDrawerProps {
  className?: string;
  onConfirmLaunch?: (planId: string, refinedGoal: string) => void;
  onClose?: () => void;
}

export const MicroPlanDrawer: React.FC<MicroPlanDrawerProps> = ({
  className = '',
  onConfirmLaunch,
  onClose,
}) => {
  const displayMode = useCompanionPlanHubStore((state) => state.displayMode);
  const activePlan = useCompanionPlanHubStore((state) => state.activePlan);
  const refinedGoal = useCompanionPlanHubStore((state) => state.refinedGoal);
  const setRefinedGoal = useCompanionPlanHubStore(
    (state) => state.setRefinedGoal
  );
  const toggleSubtaskSkip = useCompanionPlanHubStore(
    (state) => state.toggleSubtaskSkip
  );
  const confirmStartPlan = useCompanionPlanHubStore(
    (state) => state.confirmStartPlan
  );
  const setDisplayMode = useCompanionPlanHubStore(
    (state) => state.setDisplayMode
  );

  if (displayMode !== 'plan_drawer' || activePlan === null) {
    return null;
  }

  const { total, skipped } = calculatePlanProgress(activePlan.subtasks);

  const handleClose = (): void => {
    setDisplayMode('pet_only');
    if (onClose !== undefined) {
      onClose();
    }
  };

  const handleConfirm = (): void => {
    confirmStartPlan();
    if (onConfirmLaunch !== undefined) {
      onConfirmLaunch(activePlan.planId, refinedGoal);
    }
  };

  return (
    <section
      data-testid="micro-plan-drawer"
      aria-label="迷你工作台任务计划抽屉"
      className={`w-96 bg-slate-900/90 backdrop-blur-md border border-slate-700/80 rounded-2xl shadow-2xl p-4 flex flex-col gap-3.5 text-slate-200 z-50 ${className}`}
    >
      {/* 头部标题与指派智能体 */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-amber-400" />
          <h2 className="text-xs font-bold text-slate-100">
            任务执行计划书
          </h2>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-950 text-blue-300 border border-blue-800 flex items-center gap-1">
            <Bot className="w-3 h-3" />
            <span>{activePlan.targetAgentName}</span>
          </span>
        </div>

        <button
          type="button"
          data-testid="close-plan-drawer-btn"
          aria-label="关闭计划抽屉"
          onClick={handleClose}
          className="p-1 rounded text-slate-400 hover:text-slate-200 hover:bg-slate-800"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* 业务目标微调区 */}
      <div className="flex flex-col gap-1">
        <label
          htmlFor="plan-goal-input"
          className="text-[11px] font-medium text-slate-400 flex items-center gap-1"
        >
          <Edit3 className="w-3 h-3 text-blue-400" />
          <span>核心业务目标微调:</span>
        </label>
        <input
          id="plan-goal-input"
          data-testid="plan-goal-input"
          type="text"
          value={refinedGoal}
          onChange={(e) => setRefinedGoal(e.target.value)}
          placeholder="可在此补充或精简需求..."
          className="text-xs bg-slate-950 border border-slate-700/80 rounded-lg px-2.5 py-1.5 text-slate-200 focus:outline-none focus:border-blue-500"
        />
      </div>

      {/* 拆解的子任务清单 */}
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center justify-between text-[11px] text-slate-400">
          <span>拆解步骤 ({total - skipped}/{total} 项开工)</span>
          <span className="flex items-center gap-1 text-[10px] text-slate-500">
            <Clock className="w-3 h-3" />
            <span>预估 ~{activePlan.estimatedMinutes} 分钟</span>
          </span>
        </div>

        <div
          data-testid="subtask-list-container"
          className="flex flex-col gap-2 max-h-52 overflow-y-auto pr-1"
        >
          {activePlan.subtasks.map((task) => {
            const isSkipped = task.status === 'skipped';
            return (
              <div
                key={task.id}
                data-testid={`subtask-item-${task.id}`}
                className={`p-2 rounded-xl border flex items-start gap-2 text-xs transition-colors ${
                  isSkipped
                    ? 'bg-slate-950/40 border-slate-800/60 opacity-60'
                    : 'bg-slate-950/80 border-slate-800'
                }`}
              >
                <button
                  type="button"
                  data-testid={`toggle-skip-subtask-${task.id}`}
                  disabled={task.required}
                  onClick={() => toggleSubtaskSkip(task.id)}
                  aria-label={
                    task.required
                      ? '核心必选步骤不可跳过'
                      : isSkipped
                        ? '恢复执行该步骤'
                        : '跳过该步骤'
                  }
                  className="mt-0.5 text-slate-400 hover:text-slate-200 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {isSkipped ? (
                    <SkipForward className="w-3.5 h-3.5 text-amber-500" />
                  ) : (
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                  )}
                </button>

                <div className="flex-1 min-w-0">
                  <div
                    className={`font-medium ${
                      isSkipped ? 'line-through text-slate-500' : 'text-slate-200'
                    }`}
                  >
                    {task.title}
                  </div>
                  {task.description !== undefined && (
                    <div className="text-[10px] text-slate-400 mt-0.5">
                      {task.description}
                    </div>
                  )}
                </div>

                {task.required && (
                  <span className="text-[9px] px-1 py-0.5 rounded bg-slate-800 text-slate-400 shrink-0">
                    必选
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* 底部确认开工按钮 */}
      <div className="flex items-center justify-between pt-2 border-t border-slate-800">
        <button
          type="button"
          data-testid="cancel-plan-drawer-btn"
          onClick={handleClose}
          className="px-3 py-1.5 rounded-lg text-xs text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
        >
          暂不开工
        </button>

        <button
          type="button"
          data-testid="confirm-launch-plan-btn"
          onClick={handleConfirm}
          className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 text-white hover:bg-emerald-500 shadow-md transition-colors"
        >
          <Play className="w-3.5 h-3.5 fill-current" />
          <span>确认开工</span>
        </button>
      </div>
    </section>
  );
};
