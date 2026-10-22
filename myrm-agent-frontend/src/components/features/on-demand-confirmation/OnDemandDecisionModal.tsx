import React, { useEffect, useRef } from 'react';
import { HelpCircle, ArrowRight, X, MessageSquarePlus } from 'lucide-react';
import { useOnDemandConfirmationStore } from './useOnDemandConfirmationStore';
import { OnDemandOptionCard } from './OnDemandOptionCard';
import { mapKeyToOptionLetter } from './onDemandConfirmationEngine';
import { ConfirmationDecisionResult } from './onDemandConfirmationTypes';

interface OnDemandDecisionModalProps {
  onResumeInterrupt?: (decision: ConfirmationDecisionResult) => void;
}

export const OnDemandDecisionModal: React.FC<OnDemandDecisionModalProps> = ({
  onResumeInterrupt,
}) => {
  const customInputRef = useRef<HTMLTextAreaElement>(null);
  const {
    currentInterrupt,
    selectedOptionId,
    customInput,
    isModalOpen,
    selectOption,
    setCustomInput,
    closeModal,
    confirmDecision,
  } = useOnDemandConfirmationStore();

  const handleSubmit = React.useCallback(() => {
    const result = confirmDecision();
    if (result && onResumeInterrupt) {
      onResumeInterrupt(result);
    }
  }, [confirmDecision, onResumeInterrupt]);

  // 全局 1-6 / A-F 快捷键单选监听与 Enter 快速提交
  useEffect(() => {
    if (!isModalOpen || !currentInterrupt) {
      return;
    }

    const handleKeyDown = (e: KeyboardEvent) => {
      const activeEl = document.activeElement;
      const isInputActive =
        activeEl instanceof HTMLInputElement ||
        activeEl instanceof HTMLTextAreaElement;

      // 如果当前焦点在输入框中，仅拦截 Cmd+Enter 快速提交
      if (isInputActive) {
        if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
          e.preventDefault();
          handleSubmit();
        }
        return;
      }

      // 如果未在输入框中，支持 1-6 与 A-F 单选
      const targetLetter = mapKeyToOptionLetter(e.key, currentInterrupt.options);
      if (targetLetter) {
        e.preventDefault();
        selectOption(targetLetter);
        return;
      }

      // Enter 键直接提交选中项
      if (e.key === 'Enter' && selectedOptionId) {
        e.preventDefault();
        handleSubmit();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isModalOpen, currentInterrupt, selectedOptionId, selectOption, handleSubmit]);

  if (!isModalOpen || !currentInterrupt) {
    return null;
  }

  return (
    <div
      data-testid="on-demand-decision-modal"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm select-none"
    >
      <dialog
        open
        aria-modal="true"
        aria-labelledby="decision-modal-title"
        className="w-full max-w-2xl bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow-2xl flex flex-col gap-5 text-slate-200"
      >
        {/* 标题栏与关闭 */}
        <div className="flex items-start justify-between gap-4 pb-3 border-b border-slate-800/80">
          <div className="flex items-start gap-3">
            <div className="w-9 h-9 rounded-2xl bg-indigo-600/20 border border-indigo-500/40 flex items-center justify-center shrink-0 mt-0.5 text-indigo-400">
              <HelpCircle className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-semibold bg-indigo-950 text-indigo-300 border border-indigo-800">
                  按需决策确认
                </span>
                <span className="text-xs font-mono text-slate-500">
                  任务 #{currentInterrupt.taskId}
                </span>
              </div>
              <h2
                id="decision-modal-title"
                className="mt-1 text-base font-bold text-white leading-snug"
              >
                {currentInterrupt.prompt}
              </h2>
            </div>
          </div>

          <button
            type="button"
            onClick={closeModal}
            className="p-1.5 rounded-xl hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors"
            title="暂缓决策"
            aria-label="关闭"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* 任务背景摘要 */}
        {currentInterrupt.contextSummary && (
          <p className="text-xs text-slate-400 leading-relaxed bg-slate-950/60 p-3 rounded-xl border border-slate-800/60 font-mono">
            {currentInterrupt.contextSummary}
          </p>
        )}

        {/* A-F 选项卡片列表 */}
        <div className="space-y-2.5 max-h-[340px] overflow-y-auto pr-1">
          {currentInterrupt.options.map((opt, index) => (
            <OnDemandOptionCard
              key={opt.id}
              option={opt}
              digitShortcut={index + 1}
              isSelected={selectedOptionId === opt.id}
              onSelect={selectOption}
            />
          ))}
        </div>

        {/* 自定义补充输入框 (可选) */}
        {currentInterrupt.allowCustomInput !== false && (
          <div className="pt-2">
            <label
              htmlFor="custom-decision-input"
              className="flex items-center gap-1.5 text-xs font-medium text-slate-400 mb-1.5"
            >
              <MessageSquarePlus className="w-3.5 h-3.5 text-indigo-400" />
              <span>补充自定义需求或指引（可选）</span>
            </label>
            <textarea
              id="custom-decision-input"
              ref={customInputRef}
              rows={2}
              value={customInput}
              onChange={(e) => setCustomInput(e.target.value)}
              placeholder={
                currentInterrupt.placeholder ||
                '若以上选项不完全符合，请补充具体指引（Cmd+Enter 极速提交）...'
              }
              className="w-full px-3 py-2 bg-slate-950/80 border border-slate-800 rounded-xl text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 transition-all resize-none"
            />
          </div>
        )}

        {/* 底部确认操作栏 */}
        <div className="flex items-center justify-between pt-3 border-t border-slate-800/80 text-xs">
          <div className="text-slate-500 font-mono text-[11px] hidden sm:block">
            按数字键 <kbd className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">1-6</kbd> 选定，按 <kbd className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">Enter</kbd> 提交
          </div>

          <div className="flex items-center gap-2 ml-auto">
            <button
              type="button"
              onClick={closeModal}
              className="px-4 py-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition-colors font-medium text-xs"
            >
              暂缓决策
            </button>
            <button
              type="button"
              onClick={handleSubmit}
              disabled={!selectedOptionId}
              className="flex items-center gap-1.5 px-5 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold text-xs transition-all shadow-md"
            >
              <span>确认并继续</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </dialog>
    </div>
  );
};
