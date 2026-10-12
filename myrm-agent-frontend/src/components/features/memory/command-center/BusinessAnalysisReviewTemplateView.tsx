/**
 * [INPUT]
 * @/services/memory/businessTemplates::BusinessExperienceTemplateDTO, recordTemplateValidation
 *
 * [OUTPUT]
 * BusinessAnalysisReviewTemplateView: View presenting the 3 reusable business analysis review methods
 * and template validation feedback controls.
 *
 * [POS]
 * Sub-view of Item 107 BusinessScenarioTemplatesCard.
 * Strict typing applied, zero any, file length < 300 lines.
 */

import React, { useState } from 'react';
import {
  FileSpreadsheet,
  CheckCircle2,
  AlertTriangle,
  ThumbsUp,
  ThumbsDown,
  Layers,
  Sparkles,
} from 'lucide-react';
import type { BusinessExperienceTemplateDTO } from '@/services/memory/businessTemplates';
import { recordTemplateValidation } from '@/services/memory/businessTemplates';

interface BusinessAnalysisReviewTemplateViewProps {
  template: BusinessExperienceTemplateDTO;
  onTemplateUpdated: (updated: BusinessExperienceTemplateDTO) => void;
}

export const BusinessAnalysisReviewTemplateView: React.FC<
  BusinessAnalysisReviewTemplateViewProps
> = ({ template, onTemplateUpdated }) => {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [feedbackMessage, setFeedbackMessage] = useState<string | null>(null);

  const handleValidate = async (isValidated: boolean) => {
    setIsSubmitting(true);
    setFeedbackMessage(null);
    try {
      const res = await recordTemplateValidation({
        template_id: template.template_id,
        is_validated: isValidated,
        note: isValidated
          ? 'Operator confirmed review methods effective'
          : 'Operator rejected review method application',
      });
      onTemplateUpdated({
        ...template,
        validated_count: res.validated_count,
        rejected_count: res.rejected_count,
        last_validated_at: res.timestamp,
      });
      setFeedbackMessage(
        isValidated
          ? `验证成功已记录（当前有效率: ${res.validated_count} 次通过）`
          : `排斥记录已落盘（累计纠偏: ${res.rejected_count} 次）`,
      );
    } catch {
      // Offline fallback update
      const updatedCount = isValidated
        ? template.validated_count + 1
        : template.validated_count;
      const updatedRej = !isValidated
        ? template.rejected_count + 1
        : template.rejected_count;
      onTemplateUpdated({
        ...template,
        validated_count: updatedCount,
        rejected_count: updatedRej,
        last_validated_at: new Date().toISOString(),
      });
      setFeedbackMessage(
        isValidated
          ? '（本地仿真）已记录成功验证反馈'
          : '（本地仿真）已记录纠偏排斥反馈',
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Header Banner */}
      <div className="p-3.5 bg-blue-500/5 dark:bg-blue-950/20 rounded-lg border border-blue-500/20 flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <FileSpreadsheet className="w-4 h-4 text-blue-500" />
            <span className="font-semibold text-sm">{template.name}</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-600 dark:text-blue-400 font-mono">
              v{template.version}
            </span>
          </div>
          <p className="text-xs text-muted-foreground">{template.summary}</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => handleValidate(true)}
            disabled={isSubmitting}
            className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium bg-emerald-600 text-white rounded hover:bg-emerald-700 disabled:opacity-50 transition-colors focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <ThumbsUp className="w-3.5 h-3.5" />
            验证通过 ({template.validated_count})
          </button>
          <button
            type="button"
            onClick={() => handleValidate(false)}
            disabled={isSubmitting}
            className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium bg-muted text-muted-foreground rounded hover:bg-destructive/10 hover:text-destructive disabled:opacity-50 transition-colors focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <ThumbsDown className="w-3.5 h-3.5" />
            纠偏排斥 ({template.rejected_count})
          </button>
        </div>
      </div>

      {feedbackMessage && (
        <div className="text-xs p-2 bg-muted/40 rounded border border-border/50 text-foreground flex items-center gap-1.5">
          <Sparkles className="w-3.5 h-3.5 text-primary" />
          {feedbackMessage}
        </div>
      )}

      {/* 3 Reusable Review Methods */}
      <div className="space-y-2.5">
        <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
          <Layers className="w-3.5 h-3.5 text-blue-500" />
          复盘三方法执行检查规程 (复用排障方法 · 禁止复用历史旧数据)
        </h4>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {template.checklist_steps.map((step) => (
            <div
              key={step.step_index}
              className="p-3 bg-background rounded-lg border border-border/60 hover:border-blue-500/40 transition-colors flex flex-col justify-between"
            >
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-mono font-semibold px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                    Step {step.step_index}
                  </span>
                  {step.mandatory && (
                    <span className="text-[10px] text-amber-500 font-medium">
                      Mandatory
                    </span>
                  )}
                </div>
                <div className="text-xs font-semibold text-foreground">
                  {step.name}
                </div>
                <p className="text-[11px] text-muted-foreground leading-relaxed">
                  {step.description}
                </p>
              </div>

              <div className="mt-3 pt-2 border-t border-border/40">
                <span className="text-[10px] text-muted-foreground block font-mono">
                  验证准则:
                </span>
                <code className="text-[10px] text-blue-600 dark:text-blue-400 font-mono break-all">
                  {step.validation_rule}
                </code>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Boundary Conditions & Methodology Defense */}
      <div className="p-3 bg-muted/20 rounded-lg border border-border/50 space-y-2">
        <div className="text-xs font-semibold flex items-center gap-1.5 text-foreground">
          <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
          不可逾越的边界条件与反模式防御
        </div>
        <ul className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs text-muted-foreground">
          {template.boundary_conditions.map((b) => (
            <li key={b} className="flex items-start gap-1.5">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0 mt-0.5" />
              <span>{b}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
};
