'use client';

import React, { memo, useState, useMemo, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconCheck,
  IconCopy,
  IconX,
} from '@/components/features/icons/PremiumIcons';
import { Download, FileText, CheckCircle2 } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';
import type { ExecutionTrace } from '@/services/statistics';
import {
  generateEvidencePackFromTrace,
  exportEvidencePackToMarkdown,
  downloadEvidencePack,
  type EvidencePackStep,
} from '@/services/evidencePackGenerator';

interface ProjectExperienceWizardModalProps {
  trace: ExecutionTrace;
  isOpen: boolean;
  onClose: () => void;
}

export const ProjectExperienceWizardModal: React.FC<ProjectExperienceWizardModalProps> = memo(
  ({ trace, isOpen, onClose }) => {
    const t = useTranslations('common');
    const [activeStepIndex, setActiveStepIndex] = useState(0);
    const [copied, setCopied] = useState(false);

    const pack = useMemo(() => generateEvidencePackFromTrace(trace), [trace]);
    const currentStep = pack.steps[activeStepIndex] as EvidencePackStep | undefined;

    const handleCopyMarkdown = useCallback(async () => {
      const md = exportEvidencePackToMarkdown(pack);
      await writeToClipboard(md);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }, [pack]);

    const handleDownloadMd = useCallback(() => {
      downloadEvidencePack(pack, 'markdown');
    }, [pack]);

    const handleDownloadJson = useCallback(() => {
      downloadEvidencePack(pack, 'json');
    }, [pack]);

    if (!isOpen) {
      return null;
    }

    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
        <div className="relative flex flex-col w-full max-w-4xl max-h-[88vh] bg-background border border-border rounded-xl shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-200">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-border bg-muted/20">
            <div className="flex items-center gap-2">
              <FileText className="w-5 h-5 text-primary" />
              <div>
                <h2 className="text-base font-semibold text-foreground">项目实战六步经验向导 (Evidence Pack Wizard)</h2>
                <p className="text-xs text-muted-foreground truncate max-w-md">
                  {pack.taskTitle} · {pack.sessionId.slice(0, 12)}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={handleCopyMarkdown}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-border bg-background hover:bg-muted transition-colors text-foreground"
                title="复制 Markdown"
              >
                {copied ? <IconCheck className="w-3.5 h-3.5 text-emerald-500" /> : <IconCopy className="w-3.5 h-3.5" />}
                {copied ? '已复制' : '复制 MD'}
              </button>
              <button
                onClick={handleDownloadMd}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
                title="下载 Markdown"
              >
                <Download className="w-3.5 h-3.5" />
                导出 Markdown
              </button>
              <button
                onClick={handleDownloadJson}
                className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium rounded-lg border border-border bg-background hover:bg-muted transition-colors text-muted-foreground"
                title="下载 JSON"
              >
                JSON
              </button>
              <button
                onClick={onClose}
                className="p-1.5 text-muted-foreground hover:text-foreground rounded-lg hover:bg-muted transition-colors ml-2"
                aria-label={t('close')}
              >
                <IconX className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Stepper Navigation */}
          <div className="flex border-b border-border bg-muted/10 overflow-x-auto scrollbar-none">
            {pack.steps.map((step, idx) => {
              const isActive = idx === activeStepIndex;
              return (
                <button
                  key={step.id}
                  onClick={() => setActiveStepIndex(idx)}
                  className={cn(
                    'flex items-center gap-2 px-4 py-3 text-xs font-medium whitespace-nowrap transition-colors border-b-2',
                    isActive
                      ? 'border-primary text-primary bg-primary/5'
                      : 'border-transparent text-muted-foreground hover:text-foreground hover:bg-muted/30',
                  )}
                >
                  <span
                    className={cn(
                      'flex items-center justify-center w-5 h-5 rounded-full text-[10px]',
                      isActive ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground',
                    )}
                  >
                    {step.stepIndex}
                  </span>
                  <span>{step.title.split(' ')[0]}</span>
                </button>
              );
            })}
          </div>

          {/* Step Content */}
          <div className="flex-1 overflow-y-auto p-6 space-y-4">
            {currentStep && (
              <div className="space-y-4">
                <div>
                  <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                    {currentStep.title}
                  </h3>
                  <p className="text-xs text-muted-foreground mt-0.5">{currentStep.summary}</p>
                </div>

                <div className="rounded-lg border border-border/60 bg-muted/20 p-4 space-y-2">
                  <h4 className="text-xs font-medium text-foreground">关键事实与实证记录:</h4>
                  <ul className="space-y-1.5">
                    {currentStep.details.map((detail, dIdx) => (
                      <li key={dIdx} className="text-xs text-foreground/90 flex items-start gap-2">
                        <span className="text-muted-foreground mt-0.5">•</span>
                        <span className="leading-relaxed break-all">{detail}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                {currentStep.metrics && (
                  <div className="flex flex-wrap gap-3 pt-2">
                    {Object.entries(currentStep.metrics).map(([k, v]) => (
                      <div
                        key={k}
                        className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-border/60 bg-background text-xs"
                      >
                        <span className="text-muted-foreground">{k}:</span>
                        <span className="font-semibold text-foreground">{v}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Footer Navigation */}
          <div className="flex items-center justify-between px-6 py-3 border-t border-border bg-muted/10">
            <button
              onClick={() => setActiveStepIndex((prev) => Math.max(0, prev - 1))}
              disabled={activeStepIndex === 0}
              className="px-3 py-1.5 text-xs font-medium rounded-lg border border-border bg-background text-foreground hover:bg-muted transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              上一步
            </button>
            <span className="text-xs text-muted-foreground">
              步骤 {activeStepIndex + 1} / {pack.steps.length}
            </span>
            <button
              onClick={() => setActiveStepIndex((prev) => Math.min(pack.steps.length - 1, prev + 1))}
              disabled={activeStepIndex === pack.steps.length - 1}
              className="px-3 py-1.5 text-xs font-medium rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              下一步
            </button>
          </div>
        </div>
      </div>
    );
  },
);

ProjectExperienceWizardModal.displayName = 'ProjectExperienceWizardModal';
export default ProjectExperienceWizardModal;
