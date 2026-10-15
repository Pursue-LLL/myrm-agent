import React, { useEffect, useState } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  Briefcase,
  Check,
  Code2,
  Cpu,
  FileSpreadsheet,
  Key,
  MessageSquare,
  Palette,
  Sparkles,
  X,
  Zap,
} from 'lucide-react';
import {
  NON_DEV_WIZARD_STEPS,
  useConversationalConfigStore,
} from './useConversationalConfigStore';

interface NonDevZeroFrictionWizardModalProps {
  onCompleted?: (selections: Record<number, string>) => void;
  className?: string;
}

function renderStepIcon(iconName: string) {
  switch (iconName) {
    case 'briefcase':
      return <Briefcase className="h-4 w-4 text-blue-500" />;
    case 'code':
      return <Code2 className="h-4 w-4 text-purple-500" />;
    case 'palette':
      return <Palette className="h-4 w-4 text-amber-500" />;
    case 'zap':
      return <Zap className="h-4 w-4 text-yellow-500" />;
    case 'key':
      return <Key className="h-4 w-4 text-emerald-500" />;
    case 'cpu':
      return <Cpu className="h-4 w-4 text-indigo-500" />;
    case 'file-spreadsheet':
      return <FileSpreadsheet className="h-4 w-4 text-emerald-500" />;
    default:
      return <MessageSquare className="h-4 w-4 text-primary" />;
  }
}

export const NonDevZeroFrictionWizardModal: React.FC<
  NonDevZeroFrictionWizardModalProps
> = ({ onCompleted, className = '' }) => {
  const isWizardOpen = useConversationalConfigStore(
    (state) => state.isNonDevWizardOpen,
  );
  const currentStepNumber = useConversationalConfigStore(
    (state) => state.wizardCurrentStep,
  );
  const setWizardStep = useConversationalConfigStore(
    (state) => state.setWizardStep,
  );
  const toggleNonDevWizard = useConversationalConfigStore(
    (state) => state.toggleNonDevWizard,
  );

  const [selectedOptions, setSelectedOptions] = useState<
    Record<number, string>
  >({
    1: 'office',
    2: 'cloud_free',
    3: 'start_invoice',
  });

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isWizardOpen) {
        toggleNonDevWizard(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isWizardOpen, toggleNonDevWizard]);

  if (!isWizardOpen) {
    return null;
  }

  const currentStep =
    NON_DEV_WIZARD_STEPS.find((s) => s.stepNumber === currentStepNumber) ??
    NON_DEV_WIZARD_STEPS[0];

  if (!currentStep) {
    return null;
  }

  const handleSelectOption = (optionId: string) => {
    setSelectedOptions((prev) => ({
      ...prev,
      [currentStepNumber]: optionId,
    }));
  };

  const handleNext = () => {
    if (currentStepNumber < 3) {
      setWizardStep(currentStepNumber + 1);
    } else {
      if (onCompleted) {
        onCompleted(selectedOptions);
      }
      toggleNonDevWizard(false);
    }
  };

  const handlePrev = () => {
    if (currentStepNumber > 1) {
      setWizardStep(currentStepNumber - 1);
    }
  };

  return (
    <dialog
      open
      aria-label="非技术用户零摩擦极简入驻向导"
      className="fixed inset-0 z-50 m-0 flex h-full w-full items-center justify-center border-0 bg-background/80 p-4 backdrop-blur-md"
    >
      <div
        data-testid="non-dev-wizard-modal"
        className={`w-full max-w-lg rounded-2xl border border-border/80 bg-background p-5 shadow-2xl ${className}`}
      >
        {/* 头部进度条与标题 */}
        <div className="flex items-center justify-between border-b border-border/40 pb-3">
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Sparkles className="h-4 w-4" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-foreground">
                开启您的 Myrm AI 协同体验
              </h3>
              <p className="text-xs text-muted-foreground">
                三步轻松完成入驻 · 像老朋友一样对话
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={() => {
              toggleNonDevWizard(false);
            }}
            aria-label="关闭入驻向导"
            className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* 步骤指示条 */}
        <div className="mt-3 flex items-center justify-between px-1">
          {[1, 2, 3].map((step) => (
            <div key={step} className="flex flex-1 items-center">
              <div
                className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold ${
                  step === currentStepNumber
                    ? 'bg-primary text-primary-foreground shadow-xs'
                    : step < currentStepNumber
                    ? 'bg-emerald-500 text-white'
                    : 'bg-muted text-muted-foreground'
                }`}
              >
                {step < currentStepNumber ? (
                  <Check className="h-3 w-3" />
                ) : (
                  step
                )}
              </div>
              {step < 3 && (
                <div
                  className={`h-0.5 flex-1 mx-2 ${
                    step < currentStepNumber ? 'bg-emerald-500' : 'bg-muted'
                  }`}
                />
              )}
            </div>
          ))}
        </div>

        {/* 当前步骤内容 */}
        <div className="mt-4">
          <h4 className="text-sm font-semibold text-foreground">
            第 {currentStep.stepNumber} 步: {currentStep.title}
          </h4>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {currentStep.subtitle}
          </p>

          <div className="mt-3 space-y-2">
            {currentStep.options.map((opt) => {
              const isSelected = selectedOptions[currentStepNumber] === opt.id;
              return (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => {
                    handleSelectOption(opt.id);
                  }}
                  className={`flex w-full items-start gap-3 rounded-xl border p-3 text-left transition-all ${
                    isSelected
                      ? 'border-primary bg-primary/10 shadow-xs ring-1 ring-primary'
                      : 'border-border/60 bg-background hover:bg-muted/40'
                  }`}
                >
                  <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-background shadow-2xs border border-border/40">
                    {renderStepIcon(opt.icon)}
                  </div>
                  <div className="min-w-0 flex-1">
                    <span className="block text-xs font-semibold text-foreground">
                      {opt.label}
                    </span>
                    <span className="block text-[11px] text-muted-foreground mt-0.5">
                      {opt.desc}
                    </span>
                  </div>
                  {isSelected && (
                    <div className="mt-1 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground">
                      <Check className="h-2.5 w-2.5" />
                    </div>
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* 底部按钮栏 */}
        <div className="mt-5 flex items-center justify-between border-t border-border/40 pt-3 text-xs">
          <button
            type="button"
            onClick={handlePrev}
            disabled={currentStepNumber === 1}
            className="flex items-center gap-1 rounded-lg border border-border/70 px-3 py-1.5 font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors disabled:opacity-40"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            <span>上一步</span>
          </button>

          <button
            type="button"
            onClick={handleNext}
            className="flex items-center gap-1 rounded-lg bg-primary px-4 py-1.5 font-medium text-primary-foreground hover:bg-primary/90 transition-colors shadow-xs"
          >
            <span>{currentStepNumber === 3 ? '完成并立即开启' : '下一步'}</span>
            <ArrowRight className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </dialog>
  );
};
