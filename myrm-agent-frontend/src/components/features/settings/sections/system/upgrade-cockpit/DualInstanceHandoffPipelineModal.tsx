/**
 * DualInstanceHandoffPipelineModal - 五阶段原子升级流水线、双实例无感接力与一键回滚模态框
 *
 * [INPUT]
 * - isOpen: boolean 模态框打开状态
 * - currentStage: UpgradeStage 当前升级阶段
 * - steps: UpgradeStageStep[] 五阶段步进状态
 * - onClose: () => void 关闭回调
 * - onRollback: () => void 触发一键回滚回调
 *
 * [OUTPUT]
 * - DualInstanceHandoffPipelineModal: React.FC
 *
 * [POS]
 * 系统一键无感升级核心控制流水线界面。将黑盒 CLI update 升级为全程可见、
 * 具备双实例热备与 1 秒无损回滚能力的下一代 GUI 升级体验。
 */

import React from 'react';
import {
  ArrowRight,
  CheckCircle2,
  GitBranch,
  Loader2,
  RefreshCw,
  Sparkles,
  Undo2,
  X,
} from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import type { UpgradeStage, UpgradeStageStep } from './upgradeCockpitTypes';

export interface DualInstanceHandoffPipelineModalProps {
  isOpen: boolean;
  currentStage: UpgradeStage;
  steps: UpgradeStageStep[];
  onClose: () => void;
  onRollback: () => void;
}

export const DualInstanceHandoffPipelineModal: React.FC<
  DualInstanceHandoffPipelineModalProps
> = ({ isOpen, currentStage, steps, onClose, onRollback }) => {
  if (!isOpen) {
    return null;
  }

  const isComplete = currentStage === 'complete';
  const isRolledBack = currentStage === 'rolled_back';
  const isFailed = currentStage === 'failed';

  return (
    <dialog
      open
      aria-modal="true"
      data-testid="dual-instance-upgrade-modal"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm m-0 h-full w-full max-h-none max-w-none border-0"
    >
      <div className="relative w-full max-w-lg overflow-hidden rounded-2xl border border-border/80 bg-background shadow-2xl animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border/50 px-5 py-4 bg-muted/20">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <RefreshCw className={cn('h-4 w-4', !isComplete && !isRolledBack && 'animate-spin')} />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-foreground">
                双实例无感升级流水线
              </h3>
              <p className="text-[11px] text-muted-foreground">
                Blue-Green 原子接力与一键秒级快照回滚
              </p>
            </div>
          </div>

          <button
            type="button"
            data-testid="close-upgrade-modal-btn"
            onClick={onClose}
            className="rounded-lg p-1 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-5 space-y-4">
          {/* 双实例热接力动态示意 */}
          <div className="flex items-center justify-between rounded-xl border border-border/60 bg-muted/30 p-3 text-xs">
            <div className="flex items-center gap-2">
              <span className="rounded bg-background px-2 py-1 font-mono text-[11px] text-muted-foreground border">
                旧实例 v0.21.4 (活动兜底)
              </span>
            </div>
            <div className="flex items-center gap-1 text-primary">
              <ArrowRight className="h-4 w-4 animate-pulse" />
              <span className="text-[10px] font-medium">无损切换</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="rounded bg-primary/10 px-2 py-1 font-mono text-[11px] text-primary border border-primary/20 font-semibold">
                新实例 v0.22.0 (准备接力)
              </span>
            </div>
          </div>

          {/* 五阶段步骤进度列表 */}
          <div className="space-y-2.5">
            {steps.map((step, idx) => {
              const isRunning = step.status === 'running';
              const isFinished = step.status === 'completed';
              const isStepFailed = step.status === 'failed';

              return (
                <div
                  key={step.stage}
                  data-testid={`pipeline-step-${step.stage}`}
                  className={cn(
                    'flex items-start gap-3 rounded-lg border p-2.5 transition-all text-xs',
                    isRunning && 'border-primary/60 bg-primary/5 shadow-sm',
                    isFinished && 'border-border/40 bg-muted/10 opacity-90',
                    isStepFailed && 'border-rose-500/40 bg-rose-500/10',
                    !isRunning && !isFinished && !isStepFailed && 'border-border/30 opacity-60',
                  )}
                >
                  <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-muted font-mono text-[10px] mt-0.5">
                    {isFinished ? (
                      <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                    ) : isRunning ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
                    ) : (
                      idx + 1
                    )}
                  </div>

                  <div className="flex-1 space-y-0.5">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-foreground">
                        {step.title}
                      </span>
                      {isRunning && (
                        <span className="font-mono text-[10px] text-primary font-medium">
                          执行中...
                        </span>
                      )}
                      {isFinished && (
                        <span className="font-mono text-[10px] text-emerald-600 dark:text-emerald-400">
                          已就绪
                        </span>
                      )}
                    </div>
                    <p className="text-[11px] text-muted-foreground leading-relaxed">
                      {step.description}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>

          {/* 升级成功高光提示 */}
          {isComplete && (
            <div
              data-testid="upgrade-complete-banner"
              className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3.5 text-xs text-emerald-900 dark:text-emerald-200 space-y-1.5"
            >
              <div className="flex items-center gap-1.5 font-semibold text-emerald-800 dark:text-emerald-300">
                <Sparkles className="h-4 w-4 text-emerald-500" />
                <span>升级完成！新实例已原子接替服务</span>
              </div>
              <p className="text-[11px] text-muted-foreground">
                已自动完成沙箱健康度自检与数据库迁移，全量会话与记忆无损保留。
              </p>
            </div>
          )}

          {/* 回滚提示 */}
          {isRolledBack && (
            <div
              data-testid="upgrade-rollback-banner"
              className="rounded-xl border border-blue-500/30 bg-blue-500/10 p-3.5 text-xs text-blue-900 dark:text-blue-200"
            >
              <div className="flex items-center gap-1.5 font-semibold">
                <Undo2 className="h-4 w-4 text-blue-500" />
                <span>已原子回滚至上一稳定版本快照</span>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-border/50 px-5 py-3.5 bg-muted/20">
          <button
            type="button"
            data-testid="rollback-trigger-btn"
            disabled={!isComplete && !isFailed}
            onClick={onRollback}
            className="flex items-center gap-1 rounded-md border border-border px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-40"
          >
            <Undo2 className="h-3 w-3" />
            <span>一键秒级原子回滚</span>
          </button>

          <button
            type="button"
            data-testid="confirm-finish-btn"
            onClick={onClose}
            className="flex items-center gap-1 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground shadow-sm hover:bg-primary/90 transition-colors"
          >
            <GitBranch className="h-3 w-3" />
            <span>{isComplete ? '体验新版本' : '关闭窗口'}</span>
          </button>
        </div>
      </div>
    </dialog>
  );
};
