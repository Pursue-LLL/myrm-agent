import React, { useEffect } from 'react';
import {
  ArrowRight,
  Check,
  FileSpreadsheet,
  Layers,
  Sparkles,
  Wrench,
  X,
  Zap,
} from 'lucide-react';
import { generatePrefilledPrompt } from './nonCodingPlaybookEngine';
import { PlaybookScenario } from './nonCodingPlaybookTypes';
import { useNonCodingPlaybookStore } from './useNonCodingPlaybookStore';

interface PlaybookPrefillModalProps {
  onPrefillSubmit?: (prompt: string, scenario: PlaybookScenario) => void;
  className?: string;
}

export const PlaybookPrefillModal: React.FC<PlaybookPrefillModalProps> = ({
  onPrefillSubmit,
  className = '',
}) => {
  const activeScenario = useNonCodingPlaybookStore(
    (state) => state.activeScenarioModal,
  );
  const formValues = useNonCodingPlaybookStore((state) => state.formValues);
  const closeScenarioModal = useNonCodingPlaybookStore(
    (state) => state.closeScenarioModal,
  );
  const updateFormField = useNonCodingPlaybookStore(
    (state) => state.updateFormField,
  );

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && activeScenario) {
        closeScenarioModal();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [activeScenario, closeScenarioModal]);

  if (!activeScenario) {
    return null;
  }

  const generatedPrompt = generatePrefilledPrompt(activeScenario, formValues);

  const handleSubmit = () => {
    if (onPrefillSubmit) {
      onPrefillSubmit(generatedPrompt, activeScenario);
    }
    closeScenarioModal();
  };

  return (
    <dialog
      open
      aria-label="一键参数装填与工作流执行向导"
      className="fixed inset-0 z-50 m-0 flex h-full w-full items-center justify-center border-0 bg-background/80 p-4 backdrop-blur-md"
    >
      <div
        data-testid="playbook-prefill-modal"
        className={`w-full max-w-2xl rounded-2xl border border-border/80 bg-background p-5 shadow-2xl ${className}`}
      >
        {/* 标题栏 */}
        <div className="flex items-center justify-between border-b border-border/40 pb-3">
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Zap className="h-4 w-4" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-foreground">
                {activeScenario.title}
              </h3>
              <p className="text-xs text-muted-foreground">
                定制参数并装填为高精度 Agent 提示词
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={closeScenarioModal}
            aria-label="关闭向导弹窗"
            className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* 主体表单区 */}
        <div className="mt-3.5 max-h-[60vh] space-y-3.5 overflow-y-auto pr-1 text-xs">
          {/* 执行蓝图 */}
          <div className="rounded-xl border border-primary/20 bg-primary/5 p-3">
            <span className="font-semibold text-primary block mb-1.5">
              自动化执行蓝图 (Pipeline Steps):
            </span>
            <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
              {activeScenario.pipelineFlow.map((step, idx) => (
                <div
                  key={step}
                  className="flex items-center gap-2 rounded bg-background/80 px-2 py-1 text-[11px] text-muted-foreground border border-border/30"
                >
                  <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-primary/15 font-mono text-[9px] text-primary">
                    {idx + 1}
                  </span>
                  <span className="truncate">{step}</span>
                </div>
              ))}
            </div>
          </div>

          {/* 参数表单 */}
          <div className="space-y-3">
            <span className="font-semibold text-foreground block">
              场景关键参数配置:
            </span>

            {activeScenario.parameters.map((param) => {
              const currentVal =
                formValues[param.id] ?? param.defaultValue ?? '';

              return (
                <div key={param.id} className="space-y-1">
                  <label
                    htmlFor={`param-input-${param.id}`}
                    className="block text-xs font-medium text-foreground"
                  >
                    {param.label}
                    {param.required && (
                      <span className="text-destructive ml-0.5">*</span>
                    )}
                  </label>

                  {param.type === 'select' && param.options ? (
                    <select
                      id={`param-input-${param.id}`}
                      value={currentVal}
                      onChange={(e) => {
                        updateFormField(param.id, e.target.value);
                      }}
                      className="w-full rounded-lg border border-border/70 bg-background px-3 py-1.5 text-xs text-foreground focus:outline-hidden focus:ring-1 focus:ring-primary"
                    >
                      {param.options.map((opt) => (
                        <option key={opt} value={opt}>
                          {opt}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      id={`param-input-${param.id}`}
                      type="text"
                      value={currentVal}
                      placeholder={param.placeholder}
                      onChange={(e) => {
                        updateFormField(param.id, e.target.value);
                      }}
                      className="w-full rounded-lg border border-border/70 bg-background px-3 py-1.5 text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-hidden focus:ring-1 focus:ring-primary"
                    />
                  )}
                </div>
              );
            })}
          </div>

          {/* 即时预览生成的 Prompt */}
          <div className="space-y-1 pt-1">
            <span className="flex items-center gap-1 font-semibold text-foreground">
              <Sparkles className="h-3 w-3 text-amber-500" />
              <span>最终生成的指令预览 (Prompt Preview):</span>
            </span>
            <div className="rounded-lg border border-border/50 bg-muted/40 p-2.5 font-mono text-[11px] text-foreground/90 leading-relaxed whitespace-pre-wrap">
              {generatedPrompt}
            </div>
          </div>
        </div>

        {/* 底部按钮栏 */}
        <div className="mt-4 flex items-center justify-between border-t border-border/40 pt-3">
          <button
            type="button"
            onClick={closeScenarioModal}
            className="rounded-lg border border-border/70 px-3.5 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
          >
            取消
          </button>

          <button
            type="button"
            onClick={handleSubmit}
            className="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors shadow-xs"
          >
            <Zap className="h-3.5 w-3.5" />
            <span>装填并立即执行</span>
            <ArrowRight className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </dialog>
  );
};
