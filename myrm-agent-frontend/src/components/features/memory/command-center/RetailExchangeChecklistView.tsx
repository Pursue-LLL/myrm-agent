/**
 * [INPUT]
 * @/services/memory/businessTemplates::BusinessExperienceTemplateDTO
 *
 * [OUTPUT]
 * RetailExchangeChecklistView: Interactive checklist view for retail exchange workflows
 * ("先问 -> 必查 -> 显式确认 -> 办理 -> 告知后续").
 *
 * [POS]
 * Sub-view of Item 107 BusinessScenarioTemplatesCard.
 * Strict typing applied, zero any, file length < 300 lines.
 */

import React, { useState } from 'react';
import {
  ShoppingBag,
  CheckCircle2,
  Circle,
  ArrowRight,
  ShieldAlert,
  RotateCcw,
  CheckSquare,
} from 'lucide-react';
import type { BusinessExperienceTemplateDTO } from '@/services/memory/businessTemplates';

interface RetailExchangeChecklistViewProps {
  template: BusinessExperienceTemplateDTO;
}

export const RetailExchangeChecklistView: React.FC<
  RetailExchangeChecklistViewProps
> = ({ template }) => {
  const [completedSteps, setCompletedSteps] = useState<number[]>([1, 2]);

  const toggleStep = (stepIndex: number) => {
    setCompletedSteps((prev) =>
      prev.includes(stepIndex)
        ? prev.filter((idx) => idx !== stepIndex)
        : [...prev, stepIndex].sort((a, b) => a - b),
    );
  };

  const handleResetChecklist = () => {
    setCompletedSteps([]);
  };

  const handleCompleteAll = () => {
    setCompletedSteps(template.checklist_steps.map((s) => s.step_index));
  };

  const allPassed =
    completedSteps.length === template.checklist_steps.length &&
    template.checklist_steps.length > 0;

  return (
    <div className="space-y-4">
      {/* Header and Controls */}
      <div className="p-3.5 bg-emerald-500/5 dark:bg-emerald-950/20 rounded-lg border border-emerald-500/20 flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <ShoppingBag className="w-4 h-4 text-emerald-500" />
            <span className="font-semibold text-sm">{template.name}</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-mono">
              {template.checklist_steps.length} 阶段标准全链路
            </span>
          </div>
          <p className="text-xs text-muted-foreground">{template.summary}</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleCompleteAll}
            className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium bg-emerald-600 text-white rounded hover:bg-emerald-700 transition-colors focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <CheckSquare className="w-3.5 h-3.5" />
            一键全部勾选
          </button>
          <button
            type="button"
            onClick={handleResetChecklist}
            className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium bg-muted text-muted-foreground rounded hover:bg-muted/80 transition-colors focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            重置步骤
          </button>
        </div>
      </div>

      {/* Five-Stage Stepper View */}
      <div className="space-y-2.5">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
            执行阶段检查清单 (进度: {completedSteps.length} /{' '}
            {template.checklist_steps.length})
          </span>
          {allPassed && (
            <span className="text-xs text-emerald-600 dark:text-emerald-400 font-medium flex items-center gap-1">
              <CheckCircle2 className="w-3.5 h-3.5" />
              全链路规程满足，允许办理换货
            </span>
          )}
        </div>

        <div className="space-y-2">
          {template.checklist_steps.map((step) => {
            const isCompleted = completedSteps.includes(step.step_index);
            return (
              <div
                key={step.step_index}
                className={`p-3 rounded-lg border transition-all flex flex-col md:flex-row md:items-center justify-between gap-3 ${
                  isCompleted
                    ? 'bg-background/80 border-emerald-500/40 shadow-sm'
                    : 'bg-muted/10 border-border/60 opacity-80 hover:opacity-100'
                }`}
              >
                <div className="flex items-start gap-3">
                  <button
                    type="button"
                    onClick={() => toggleStep(step.step_index)}
                    aria-label={`Toggle Step ${step.step_index} ${step.name}`}
                    className="p-1 text-muted-foreground hover:text-foreground focus:outline-none focus:ring-2 focus:ring-primary rounded mt-0.5"
                  >
                    {isCompleted ? (
                      <CheckCircle2 className="w-5 h-5 text-emerald-500" />
                    ) : (
                      <Circle className="w-5 h-5 text-muted-foreground" />
                    )}
                  </button>
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold text-foreground">
                        阶段 {step.step_index}: {step.name}
                      </span>
                      {step.mandatory && (
                        <span className="text-[10px] text-amber-500 font-mono">
                          [强制校验]
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {step.description}
                    </p>
                  </div>
                </div>

                <div className="text-right shrink-0 md:pl-4 md:border-l md:border-border/40">
                  <span className="text-[10px] text-muted-foreground block font-mono">
                    谓词判定式
                  </span>
                  <code className="text-[11px] text-emerald-600 dark:text-emerald-400 font-mono">
                    {step.validation_rule}
                  </code>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Safety Boundary Notice */}
      <div className="p-3 bg-amber-500/5 dark:bg-amber-950/20 rounded-lg border border-amber-500/20 flex items-start gap-2.5">
        <ShieldAlert className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
        <div className="text-xs space-y-1 text-muted-foreground">
          <div className="font-semibold text-foreground">
            τ²-bench 核心规则约束：
          </div>
          <div>
            1.
            未调用库存接口确认有货前，严禁告知用户可以换货并索取寄回地址。
          </div>
          <div>
            2.
            在第 3 阶段（显式确认）完成前，严禁调用后台
            <code className="px-1 py-0.5 mx-1 rounded bg-muted text-foreground font-mono">
              commit_exchange
            </code>
            工具。
          </div>
        </div>
      </div>
    </div>
  );
};
