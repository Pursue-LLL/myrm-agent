import React, { useState } from 'react';
import {
  HelpCircle,
  X,
  Check,
  FastForward,
  CheckCircle2,
  FileCheck2,
  Sparkles,
  Info,
} from 'lucide-react';
import { useClarificationGateStore } from './useClarificationGateStore';
import type { GoalSpec } from './clarificationGateTypes';

export interface ClarificationGateDrawerProps {
  onConfirmSpec?: (spec: GoalSpec) => void;
  className?: string;
}

export function ClarificationGateDrawer({
  onConfirmSpec,
  className = '',
}: ClarificationGateDrawerProps) {
  const isOpen = useClarificationGateStore((s) => s.isOpen);
  const closeGate = useClarificationGateStore((s) => s.closeGate);
  const rawInput = useClarificationGateStore((s) => s.rawInput);
  const questions = useClarificationGateStore((s) => s.questions);
  const answers = useClarificationGateStore((s) => s.answers);
  const customNotes = useClarificationGateStore((s) => s.customNotes);
  const setCustomNotes = useClarificationGateStore((s) => s.setCustomNotes);
  const toggleOption = useClarificationGateStore((s) => s.toggleOption);
  const skipClarification = useClarificationGateStore((s) => s.skipClarification);
  const compileGoalSpec = useClarificationGateStore((s) => s.compileGoalSpec);

  const [localNotes, setLocalNotes] = useState(customNotes);

  if (!isOpen) {
    return null;
  }

  function handleSkip() {
    const spec = skipClarification();
    if (onConfirmSpec) {
      onConfirmSpec(spec);
    }
  }

  function handleConfirm() {
    setCustomNotes(localNotes);
    const spec = compileGoalSpec();
    if (onConfirmSpec) {
      onConfirmSpec(spec);
    }
  }

  return (
    <dialog
      open
      aria-modal="true"
      aria-label="苏格拉底式需求澄清门禁抽屉"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm border-0 w-full h-full m-0 max-w-none max-h-none"
    >
      <section
        role="document"
        aria-label="需求澄清问卷与规格提炼器"
        className={`flex flex-col w-full max-w-2xl max-h-[88vh] rounded-xl border border-border bg-card shadow-2xl text-xs overflow-hidden animate-in zoom-in-95 duration-150 ${className}`}
      >
        {/* 抽屉头部 */}
        <header className="flex items-center justify-between px-5 py-3.5 border-b border-border/80 bg-muted/30">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="p-1.5 rounded-lg bg-primary/10 text-primary shrink-0">
              <HelpCircle className="w-4 h-4" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold text-foreground truncate">
                  苏格拉底式需求反向澄清门禁
                </h3>
                <span className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-primary/10 text-primary text-[10px] font-medium border border-primary/20 shrink-0">
                  <Sparkles className="w-2.5 h-2.5" />
                  <span>/grill-me 规格就绪</span>
                </span>
              </div>
              <p className="text-[11px] text-muted-foreground truncate mt-0.5">
                原始需求：“{rawInput}” · 快速点选关键维度，防止长程执行偏航
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={closeGate}
            className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            aria-label="关闭澄清抽屉"
          >
            <X className="w-4 h-4" />
          </button>
        </header>

        {/* 提示 Banner */}
        <div className="px-5 py-2.5 bg-sky-500/10 border-b border-sky-500/20 text-sky-700 dark:text-sky-300 flex items-start gap-2 text-[11px]">
          <Info className="w-3.5 h-3.5 shrink-0 mt-0.5" />
          <span>
            不想做选择题？可随时点击下方「跳过提问直接开始」，系统将以稳健的现代化 Web 极简架构假设开始，并于首轮明确通报。
          </span>
        </div>

        {/* 核心问题与选项列表 */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {questions.map((question) => {
            const selected = answers[question.id] ?? [];
            return (
              <div
                key={question.id}
                className="p-3.5 rounded-lg border border-border/60 bg-muted/10 space-y-2.5"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <h4 className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                      <span>{question.title}</span>
                      <span className="text-[10px] text-muted-foreground font-normal">
                        ({question.isMultiSelect ? '可多选' : '单选'})
                      </span>
                    </h4>
                    {question.subtitle && (
                      <p className="text-[11px] text-muted-foreground mt-0.5">
                        {question.subtitle}
                      </p>
                    )}
                  </div>
                </div>

                {/* 选项胶囊列表 */}
                <div className="flex flex-wrap gap-2 pt-1">
                  {question.options.map((option) => {
                    const isChecked = selected.includes(option.id);
                    return (
                      <button
                        key={option.id}
                        type="button"
                        aria-pressed={isChecked}
                        onClick={() => {
                          toggleOption(question.id, option.id, question.isMultiSelect);
                        }}
                        className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors border select-none ${
                          isChecked
                            ? 'bg-primary text-primary-foreground border-primary shadow-xs'
                            : 'bg-background hover:bg-muted text-foreground border-border/80'
                        }`}
                      >
                        {isChecked ? (
                          <Check className="w-3.5 h-3.5 shrink-0" />
                        ) : (
                          <div className="w-3.5 h-3.5 rounded-full border border-muted-foreground/30 shrink-0" />
                        )}
                        <span>{option.label}</span>
                        {option.isRecommended && (
                          <span
                            className={`text-[9px] px-1 py-0.2 rounded font-normal uppercase ${
                              isChecked
                                ? 'bg-primary-foreground/20 text-primary-foreground'
                                : 'bg-primary/10 text-primary'
                            }`}
                          >
                            推荐
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}

          {/* 补充约束输入框 */}
          <div className="space-y-1.5 pt-1">
            <label
              htmlFor="custom-clarification-notes"
              className="block text-xs font-semibold text-foreground"
            >
              其他自定义约束或业务背景补充（可选）
            </label>
            <textarea
              id="custom-clarification-notes"
              rows={2}
              value={localNotes}
              onChange={(e) => {
                setLocalNotes(e.target.value);
              }}
              placeholder="例如：需支持离线使用、已有现有 SQL Schema、严禁引入第三方 UI 库..."
              className="w-full text-xs p-2.5 rounded-md border border-border bg-background text-foreground outline-none focus:border-primary placeholder:text-muted-foreground/60 resize-none"
            />
          </div>
        </div>

        {/* 底部操作工具栏 */}
        <footer className="flex items-center justify-between px-5 py-3 border-t border-border/80 bg-muted/40">
          <button
            type="button"
            onClick={handleSkip}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          >
            <FastForward className="w-3.5 h-3.5" />
            <span>跳过提问，按推荐默认启动</span>
          </button>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={closeGate}
              className="px-3 py-1.5 rounded-md text-xs text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            >
              取消
            </button>
            <button
              type="button"
              onClick={handleConfirm}
              className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-md bg-primary text-primary-foreground font-medium text-xs hover:bg-primary/90 transition-colors shadow-sm"
            >
              <FileCheck2 className="w-3.5 h-3.5" />
              <span>提炼无歧义 Goal Spec 并启动</span>
            </button>
          </div>
        </footer>
      </section>
    </dialog>
  );
}
