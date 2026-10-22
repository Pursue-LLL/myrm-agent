'use client';
/* oxlint-disable jsx-a11y/prefer-tag-over-role */

/**
 * PreFlightAlignmentModal Component.
 * Structured preference alignment dialog before code streaming.
 * Adheres to AskQuestion protocol, Plan-Before-Execute gate, and zero emojis.
 */

import React, { useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  Check,
  CheckCircle2,
  ChevronRight,
  HelpCircle,
  Layers,
  Palette,
  Sliders,
  Sparkles,
  Workflow,
  X,
} from 'lucide-react';
import {
  AlignmentOption,
  AlignmentQuestion,
  AlignmentSubmission,
  DEFAULT_ALIGNMENT_QUESTIONS,
} from './alignmentTypes';

interface PreFlightAlignmentModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (submission: AlignmentSubmission) => void;
  taskTitle?: string;
  questions?: AlignmentQuestion[];
}

export const PreFlightAlignmentModal: React.FC<PreFlightAlignmentModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  taskTitle = '新可视化与课件生成任务',
  questions = DEFAULT_ALIGNMENT_QUESTIONS,
}) => {
  let t = (key: string): string => key;
  try {
    const translation = useTranslations('skillAlignment');
    t = (key: string): string => translation(key);
  } catch {
    // Fallback in test suites
  }

  const [selectedOptions, setSelectedOptions] = useState<Record<string, string[]>>({
    palette: ['tech_blue'],
    layout: ['single_interactive'],
    interaction: ['dynamic_filtering'],
  });
  const [customNotes, setCustomNotes] = useState<string>('');
  const [planBeforeExecute, setPlanBeforeExecute] = useState<boolean>(true);

  const toggleOption = (questionId: string, optionId: string, allowMultiple = false): void => {
    setSelectedOptions((prev) => {
      const current = prev[questionId] || [];
      if (!allowMultiple) {
        return { ...prev, [questionId]: [optionId] };
      }
      if (current.includes(optionId)) {
        return { ...prev, [questionId]: current.filter((id) => id !== optionId) };
      }
      return { ...prev, [questionId]: [...current, optionId] };
    });
  };

  const compiledPromptConstraint = useMemo(() => {
    const parts: string[] = [];
    questions.forEach((q) => {
      const selected = selectedOptions[q.id] || [];
      if (selected.length > 0) {
        const labels = selected
          .map((optId) => q.options.find((o) => o.id === optId)?.label || optId)
          .join(', ');
        parts.push(`${q.prompt.split(' ')[0]}: ${labels}`);
      }
    });
    if (customNotes.trim()) {
      parts.push(`定制要求: ${customNotes.trim()}`);
    }
    if (planBeforeExecute) {
      parts.push('模式: 先规划再执行 (必须先输出结构化线框方案)');
    }
    return `[前置设计偏好对齐 | ${parts.join(' | ')}]`;
  }, [questions, selectedOptions, customNotes, planBeforeExecute]);

  const handleConfirm = (): void => {
    onSubmit({
      taskSummary: taskTitle,
      selectedOptions,
      customNotes,
      planBeforeExecute,
      compiledPromptConstraint,
    });
    onClose();
  };

  if (!isOpen) {
    return null;
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="alignment-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 overflow-y-auto"
    >
      <div className="relative w-full max-w-2xl rounded-2xl bg-slate-900 border border-slate-800 shadow-2xl flex flex-col max-h-[90vh] overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800/80 bg-slate-950/40">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-indigo-500/10 text-indigo-400">
              <Sliders className="w-5 h-5" />
            </div>
            <div>
              <h2 id="alignment-modal-title" className="text-base font-semibold text-slate-100">
                {t('title')}
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">{t('subtitle')}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Plan Before Execute Gate Toggle */}
          <div className="flex items-center justify-between p-4 rounded-xl bg-indigo-950/20 border border-indigo-900/40">
            <div className="flex items-start gap-3">
              <div className="p-2 rounded-lg bg-indigo-500/20 text-indigo-400 mt-0.5">
                <Workflow className="w-4 h-4" />
              </div>
              <div>
                <span className="text-sm font-medium text-slate-200">
                  {t('planFirstTitle')}
                </span>
                <p className="text-xs text-slate-400 mt-0.5">{t('planFirstDesc')}</p>
              </div>
            </div>
            <button
              type="button"
              role="switch"
              aria-label={t('planFirstTitle')}
              aria-checked={planBeforeExecute}
              onClick={() => {
                setPlanBeforeExecute(!planBeforeExecute);
              }}
              className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                planBeforeExecute ? 'bg-indigo-600' : 'bg-slate-700'
              }`}
            >
              <span
                className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                  planBeforeExecute ? 'translate-x-5' : 'translate-x-0'
                }`}
              />
            </button>
          </div>

          {/* Structured Questions */}
          <div className="space-y-5">
            {questions.map((q) => {
              const selected = selectedOptions[q.id] || [];
              return (
                <div key={q.id} className="space-y-2.5">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-slate-300 flex items-center gap-2">
                      {q.id === 'palette' && <Palette className="w-4 h-4 text-sky-400" />}
                      {q.id === 'layout' && <Layers className="w-4 h-4 text-violet-400" />}
                      {q.id === 'interaction' && <Sparkles className="w-4 h-4 text-amber-400" />}
                      {q.prompt}
                    </span>
                    <span className="text-xs text-slate-500">
                      {q.allowMultiple ? '多选' : '单选'}
                    </span>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                    {q.options.map((opt: AlignmentOption) => {
                      const isChecked = selected.includes(opt.id);
                      return (
                        <button
                          key={opt.id}
                          type="button"
                          onClick={() => {
                            toggleOption(q.id, opt.id, q.allowMultiple);
                          }}
                          className={`flex items-start justify-between p-3 rounded-xl border text-left transition-all ${
                            isChecked
                              ? 'bg-indigo-600/10 border-indigo-500/60 text-slate-100 ring-1 ring-indigo-500/30'
                              : 'bg-slate-950/40 border-slate-800/80 text-slate-400 hover:border-slate-700 hover:text-slate-300'
                          }`}
                        >
                          <div className="space-y-1">
                            <div className="flex items-center gap-1.5">
                              <span className="text-xs font-medium text-slate-200">
                                {opt.label}
                              </span>
                              {opt.tag && (
                                <span className="px-1.5 py-0.5 text-[10px] rounded bg-indigo-500/20 text-indigo-300">
                                  {opt.tag}
                                </span>
                              )}
                            </div>
                            {opt.description && (
                              <p className="text-[11px] text-slate-500 line-clamp-1">
                                {opt.description}
                              </p>
                            )}
                          </div>
                          {isChecked && (
                            <CheckCircle2 className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
                          )}
                        </button>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Custom Notes Input */}
          <div className="space-y-1.5">
            <label htmlFor="custom-notes-input" className="text-xs font-medium text-slate-400">
              {t('customPlaceholder')}
            </label>
            <input
              id="custom-notes-input"
              type="text"
              value={customNotes}
              onChange={(e) => {
                setCustomNotes(e.target.value);
              }}
              placeholder="例如：支持暗色/亮色自适应，首屏带有粒子背景特效"
              className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950/60 border border-slate-800 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500/40"
            />
          </div>

          {/* Prompt Preview Box */}
          <div className="p-3 rounded-xl bg-slate-950/80 border border-slate-800/80">
            <span className="text-[11px] font-medium text-slate-400 block mb-1">
              {t('previewPrompt')}
            </span>
            <p className="text-xs font-mono text-indigo-300/90 break-all leading-relaxed">
              {compiledPromptConstraint}
            </p>
          </div>
        </div>

        {/* Footer Actions */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-800/80 bg-slate-950/40">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-xs font-medium text-slate-400 hover:text-slate-200 transition-colors"
          >
            {t('cancel')}
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-xs font-medium text-white shadow-lg shadow-indigo-600/20 transition-all active:scale-[0.98]"
          >
            <span>{t('confirm')}</span>
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
};
