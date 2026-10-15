import React, { useState } from 'react';
import {
  CheckCircle2,
  HelpCircle,
  Sparkles,
  Paperclip,
  Trash2,
  ChevronLeft,
  ChevronRight,
  Eye,
  Send,
  FileText,
  Upload,
} from 'lucide-react';
import { useClarificationQuestionnaireStore } from './useClarificationQuestionnaireStore';
import {
  ClarificationAttachment,
  QuestionOption,
  QuestionnaireQuestion,
  V1SpecContract,
} from './clarificationQuestionnaireTypes';
import { isQuestionnaireReadyToSubmit } from './clarificationQuestionnaireEngine';

export interface ClarificationQuestionnaireCardProps {
  onSubmitSpec?: (spec: V1SpecContract) => void;
  onCancel?: () => void;
  className?: string;
}

export const ClarificationQuestionnaireCard: React.FC<ClarificationQuestionnaireCardProps> = ({
  onSubmitSpec,
  onCancel,
  className = '',
}) => {
  const {
    questions,
    currentQuestionIndex,
    selectOption,
    updateCustomText,
    addAttachment,
    removeAttachment,
    applyAllRecommendations,
    setCurrentQuestionIndex,
    synthesizeAndPreviewSpec,
    submitQuestionnaire,
    reset,
  } = useClarificationQuestionnaireStore();

  const [showCustomInput, setShowCustomInput] = useState(false);

  const currentQ: QuestionnaireQuestion | undefined = questions[currentQuestionIndex];
  const totalQuestions = questions.length;
  const answeredCount = questions.filter(
    (q) => q.selectedOptionIds.length > 0 || (q.customTextAnswer && q.customTextAnswer.trim() !== '')
  ).length;

  const readyCheck = isQuestionnaireReadyToSubmit(questions);

  const handleSimulateAddAttachment = (qId: string) => {
    const dummyId = `att-${Date.now()}-${Math.random().toString(36).substring(2, 6)}`;
    const newAttachment: ClarificationAttachment = {
      id: dummyId,
      name: `需求参考截图_${Date.now().toString().slice(-4)}.png`,
      size: 1024 * 240,
      type: 'image/png',
      uploadStatus: 'ready',
    };
    addAttachment(qId, newAttachment);
  };

  const handleFinalSubmit = () => {
    if (!readyCheck.isReady) {
      if (readyCheck.unfulfilledIndex >= 0) {
        setCurrentQuestionIndex(readyCheck.unfulfilledIndex);
      }
      return;
    }
    const spec = submitQuestionnaire();
    if (onSubmitSpec) {
      onSubmitSpec(spec);
    }
  };

  if (!currentQ) {
    return null;
  }

  return (
    <div
      data-testid="clarification-questionnaire-card"
      className={`relative w-full rounded-2xl border border-indigo-500/30 bg-zinc-900/95 backdrop-blur-md p-5 shadow-2xl transition-all ${className}`}
    >
      {/* 头部进度条与一键推荐 */}
      <div className="flex items-center justify-between pb-3.5 border-b border-zinc-800">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
            <HelpCircle className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-bold text-zinc-100">需求前置澄清与 V1 目标对齐问卷</h3>
              <span className="px-2 py-0.5 rounded-full text-xs font-mono bg-zinc-800 text-zinc-300 border border-zinc-700">
                {answeredCount}/{totalQuestions} 已答
              </span>
            </div>
            <p className="text-xs text-zinc-400 mt-0.5">
              快速点选分水岭选项，AI 自动汇总克制规范并锁定目标，防发散过度设计
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => {
            applyAllRecommendations();
          }}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-emerald-300 bg-emerald-950/40 border border-emerald-500/40 hover:bg-emerald-900/50 rounded-lg transition-colors shadow-sm"
        >
          <Sparkles className="w-3.5 h-3.5" />
          一键按推荐确认全部
        </button>
      </div>

      {/* 题目分页指示器 */}
      <div className="flex items-center gap-1.5 py-3 border-b border-zinc-850">
        {questions.map((q, idx) => {
          const isCurrent = idx === currentQuestionIndex;
          const isDone = q.selectedOptionIds.length > 0;
          return (
            <button
              key={q.id}
              type="button"
              onClick={() => {
                setCurrentQuestionIndex(idx);
              }}
              aria-label={`跳转到第 ${idx + 1} 题`}
              className={`flex-1 h-1.5 rounded-full transition-all ${
                isCurrent
                  ? 'bg-indigo-500 shadow-[0_0_8px_rgba(99,102,241,0.6)]'
                  : isDone
                  ? 'bg-emerald-500/80'
                  : 'bg-zinc-800 hover:bg-zinc-700'
              }`}
              title={`跳转到第 ${idx + 1} 题`}
            />
          );
        })}
      </div>

      {/* 当前题目主卡片 */}
      <div className="my-4 space-y-3.5">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-bold text-zinc-100 font-sans">{currentQ.title}</span>
            <span className="text-[11px] px-2 py-0.5 rounded bg-zinc-800/90 text-zinc-400 border border-zinc-700/80">
              {currentQ.isMultiSelect ? '可多选' : '单选'}
            </span>
          </div>
          {currentQ.description && (
            <p className="text-xs text-zinc-400 mt-1">{currentQ.description}</p>
          )}
        </div>

        {/* 选项组 */}
        <div className="grid grid-cols-1 gap-2.5">
          {currentQ.options.map((opt: QuestionOption) => {
            const isSelected = currentQ.selectedOptionIds.includes(opt.id);
            return (
              <button
                key={opt.id}
                type="button"
                onClick={() => {
                  selectOption(currentQ.id, opt.id);
                }}
                className={`w-full text-left p-3 rounded-xl border transition-all flex items-start justify-between ${
                  isSelected
                    ? 'bg-indigo-950/40 border-indigo-500/70 shadow-[0_0_12px_rgba(99,102,241,0.15)] ring-1 ring-indigo-500/50'
                    : 'bg-zinc-950/40 border-zinc-800 hover:border-zinc-700 hover:bg-zinc-900/60'
                }`}
              >
                <div className="space-y-1 pr-3">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold text-zinc-200">{opt.label}</span>
                    {opt.isRecommended && (
                      <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                        <Sparkles className="w-2.5 h-2.5" />
                        推荐
                      </span>
                    )}
                  </div>
                  {opt.description && (
                    <p className="text-[11px] text-zinc-400 leading-normal">{opt.description}</p>
                  )}
                  {opt.nonGoalTag && (
                    <span className="inline-block text-[10px] text-zinc-500 italic">
                      排除: {opt.nonGoalTag}
                    </span>
                  )}
                </div>

                <div
                  className={`w-4 h-4 rounded-full border mt-0.5 flex items-center justify-center shrink-0 ${
                    isSelected
                      ? 'border-indigo-400 bg-indigo-600 text-white'
                      : 'border-zinc-600 bg-transparent'
                  }`}
                >
                  {isSelected && <CheckCircle2 className="w-3.5 h-3.5" />}
                </div>
              </button>
            );
          })}
        </div>

        {/* 针对该题的补充附件与自定义文本栏 (T3 Code 对标) */}
        <div className="pt-2 border-t border-zinc-850 space-y-2">
          <div className="flex items-center justify-between text-xs text-zinc-400">
            <button
              type="button"
              onClick={() => {
                setShowCustomInput(!showCustomInput);
              }}
              className="hover:text-indigo-300 flex items-center gap-1"
            >
              <FileText className="w-3.5 h-3.5" />
              {showCustomInput ? '收起补充说明' : '+ 填写该题目的补充说明或特殊需求'}
            </button>

            <button
              type="button"
              onClick={() => {
                handleSimulateAddAttachment(currentQ.id);
              }}
              className="hover:text-indigo-300 flex items-center gap-1 text-[11px]"
            >
              <Upload className="w-3 h-3" />
              上传/粘贴附件材料
            </button>
          </div>

          {showCustomInput && (
            <textarea
              value={currentQ.customTextAnswer || ''}
              onChange={(e) => {
                updateCustomText(currentQ.id, e.target.value);
              }}
              placeholder="如需补充特定逻辑、参数公式或限制条件，请在此键入..."
              className="w-full h-16 p-2.5 text-xs bg-zinc-950/80 text-zinc-200 rounded-lg border border-zinc-800 focus:outline-none focus:border-indigo-500 resize-none font-mono"
            />
          )}

          {/* 附件材料徽标列表 */}
          {currentQ.attachments.length > 0 && (
            <div className="flex flex-wrap gap-1.5 pt-1">
              {currentQ.attachments.map((att: ClarificationAttachment) => (
                <div
                  key={att.id}
                  className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs bg-zinc-800 border border-zinc-700 text-zinc-300"
                >
                  <Paperclip className="w-3 h-3 text-indigo-400" />
                  <span className="font-mono text-[11px] truncate max-w-[140px]">{att.name}</span>
                  <button
                    type="button"
                    onClick={() => {
                      removeAttachment(currentQ.id, att.id);
                    }}
                    title="移除附件"
                    className="text-zinc-500 hover:text-red-400 ml-0.5"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 底部导航与提交控制区 */}
      <div className="flex items-center justify-between pt-3 border-t border-zinc-800">
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={currentQuestionIndex === 0}
            onClick={() => {
              setCurrentQuestionIndex(currentQuestionIndex - 1);
            }}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium bg-zinc-800 text-zinc-300 hover:bg-zinc-750 disabled:opacity-30 disabled:cursor-not-allowed border border-zinc-700 transition-colors"
          >
            <ChevronLeft className="w-3.5 h-3.5" />
            上一题
          </button>
          <button
            type="button"
            disabled={currentQuestionIndex === totalQuestions - 1}
            onClick={() => {
              setCurrentQuestionIndex(currentQuestionIndex + 1);
            }}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium bg-zinc-800 text-zinc-300 hover:bg-zinc-750 disabled:opacity-30 disabled:cursor-not-allowed border border-zinc-700 transition-colors"
          >
            下一题
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => {
              synthesizeAndPreviewSpec();
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 transition-colors"
          >
            <Eye className="w-3.5 h-3.5 text-indigo-400" />
            预览克制 V1 规范
          </button>

          <button
            type="button"
            onClick={handleFinalSubmit}
            disabled={!readyCheck.isReady}
            className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed shadow-md transition-colors"
          >
            <Send className="w-3.5 h-3.5" />
            锁定规范并启动 (Enter)
          </button>
        </div>
      </div>
    </div>
  );
};
