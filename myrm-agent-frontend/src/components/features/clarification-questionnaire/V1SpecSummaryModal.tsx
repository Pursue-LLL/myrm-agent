import React from 'react';
import {
  X,
  Target,
  ShieldCheck,
  Ban,
  CheckCircle2,
  Copy,
  Layers,
} from 'lucide-react';
import { useClarificationQuestionnaireStore } from './useClarificationQuestionnaireStore';
import { V1SpecContract } from './clarificationQuestionnaireTypes';

export interface V1SpecSummaryModalProps {
  onConfirmLockIn?: (spec: V1SpecContract) => void;
  className?: string;
}

export const V1SpecSummaryModal: React.FC<V1SpecSummaryModalProps> = ({
  onConfirmLockIn,
  className = '',
}) => {
  const {
    isSpecModalOpen,
    activeSpecContract,
    setSpecModalOpen,
    submitQuestionnaire,
  } = useClarificationQuestionnaireStore();

  if (!isSpecModalOpen || !activeSpecContract) {
    return null;
  }

  const handleClose = () => {
    setSpecModalOpen(false);
  };

  const handleConfirm = () => {
    const finalSpec = submitQuestionnaire();
    if (onConfirmLockIn) {
      onConfirmLockIn(finalSpec);
    }
  };

  const handleCopyPrompt = () => {
    if (navigator.clipboard) {
      void navigator.clipboard.writeText(activeSpecContract.generatedPromptText);
    }
  };

  return (
    <div
      data-testid="v1-spec-summary-modal"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-fade-in"
    >
      <div
        className={`relative w-full max-w-xl rounded-2xl border border-zinc-800 bg-zinc-900 shadow-2xl p-6 overflow-hidden ${className}`}
      >
        {/* 头部标题与关闭 */}
        <div className="flex items-center justify-between pb-4 border-b border-zinc-800">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              <Target className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-zinc-100">
                克制 V1 需求规范契约 (Goal Lock-in)
              </h3>
              <p className="text-xs text-zinc-400 mt-0.5">
                已自动将您的问卷答案汇总为防发散准入协议，严格防范过度设计
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={handleClose}
            className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* 核心契约展示体 */}
        <div className="my-4 max-h-[60vh] overflow-y-auto space-y-4 pr-1">
          {/* 1. 目标形态 */}
          <div className="p-3 rounded-xl bg-zinc-950/60 border border-zinc-800/80">
            <div className="flex items-center gap-2 text-xs font-semibold text-zinc-300 mb-1">
              <Layers className="w-4 h-4 text-indigo-400" />
              目标运行形态:
            </div>
            <div className="text-xs text-zinc-200 font-mono pl-6">
              {activeSpecContract.productShape}
            </div>
          </div>

          {/* 2. 核心功能准入 */}
          <div className="p-3 rounded-xl bg-zinc-950/60 border border-zinc-800/80">
            <div className="flex items-center gap-2 text-xs font-semibold text-emerald-400 mb-1.5">
              <ShieldCheck className="w-4 h-4" />
              核心首发功能准入 (MVP Scope):
            </div>
            <ul className="list-disc list-inside text-xs text-zinc-300 space-y-1 pl-1">
              {activeSpecContract.coreCapabilities.length === 0 ? (
                <li className="text-zinc-500 italic">基础核心业务流</li>
              ) : (
                activeSpecContract.coreCapabilities.map((cap, idx) => (
                  <li key={`cap-${idx}`} className="leading-relaxed">
                    {cap}
                  </li>
                ))
              )}
            </ul>
          </div>

          {/* 3. 明确排除项 Non-goals */}
          <div className="p-3 rounded-xl bg-red-950/20 border border-red-500/20">
            <div className="flex items-center gap-2 text-xs font-semibold text-red-400 mb-1.5">
              <Ban className="w-4 h-4" />
              明确排除不做项 (Non-goals · 防过度设计):
            </div>
            <ul className="list-disc list-inside text-xs text-zinc-300 space-y-1 pl-1">
              {activeSpecContract.nonGoals.length === 0 ? (
                <li className="text-zinc-500 italic">本轮未声明排除项</li>
              ) : (
                activeSpecContract.nonGoals.map((ng, idx) => (
                  <li key={`ng-${idx}`} className="leading-relaxed text-red-200/90">
                    {ng}
                  </li>
                ))
              )}
            </ul>
          </div>

          {/* 4. 生成的完整 Prompt 预览 */}
          <div className="p-3 rounded-xl bg-zinc-950 border border-zinc-800">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[11px] font-semibold text-zinc-400">
                注入智能体上下文的契约文本:
              </span>
              <button
                type="button"
                onClick={handleCopyPrompt}
                className="inline-flex items-center gap-1 text-[11px] text-indigo-400 hover:text-indigo-300"
              >
                <Copy className="w-3 h-3" />
                复制文本
              </button>
            </div>
            <pre className="text-[11px] font-mono text-zinc-300 bg-zinc-900 p-2.5 rounded-lg overflow-x-auto whitespace-pre-wrap leading-relaxed">
              {activeSpecContract.generatedPromptText}
            </pre>
          </div>
        </div>

        {/* 底部确认操作条 */}
        <div className="flex items-center justify-end gap-3 pt-4 border-t border-zinc-800">
          <button
            type="button"
            onClick={handleClose}
            className="px-4 py-2 text-xs font-medium text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            返回调整问卷
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold bg-indigo-600 text-white hover:bg-indigo-500 shadow-lg shadow-indigo-600/30 transition-colors"
          >
            <CheckCircle2 className="w-4 h-4" />
            锁定契约并启动任务
          </button>
        </div>
      </div>
    </div>
  );
};
