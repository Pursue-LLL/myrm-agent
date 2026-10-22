import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { Sparkles, ChevronRight, ChevronLeft, X, Check, Compass } from 'lucide-react';
import { useVisualTourStore } from './useVisualTourStore';
import { calculateSpotlightRect } from './visualTourEngine';
import type { SpotlightRect } from './visualTourTypes';

export const InteractiveFeatureSpotlightTour: React.FC = () => {
  const {
    isTourActive,
    currentStepIndex,
    steps,
    nextTourStep,
    prevTourStep,
    skipTour,
    finishTour,
  } = useVisualTourStore();

  const [rect, setRect] = useState<SpotlightRect | null>(null);

  const currentStep = useMemo(() => {
    return steps[currentStepIndex] ?? null;
  }, [steps, currentStepIndex]);

  const updateTargetRect = useCallback(() => {
    if (!currentStep || !currentStep.targetSelector) {
      setRect(null);
      return;
    }
    const element = document.querySelector(currentStep.targetSelector);
    const calculated = calculateSpotlightRect(element);
    setRect(calculated);
  }, [currentStep]);

  useEffect(() => {
    if (!isTourActive) {
      return;
    }
    updateTargetRect();
    window.addEventListener('resize', updateTargetRect);
    window.addEventListener('scroll', updateTargetRect, true);

    return () => {
      window.removeEventListener('resize', updateTargetRect);
      window.removeEventListener('scroll', updateTargetRect, true);
    };
  }, [isTourActive, updateTargetRect]);

  useEffect(() => {
    if (!isTourActive) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        skipTour();
      } else if (event.key === 'ArrowRight') {
        event.preventDefault();
        nextTourStep();
      } else if (event.key === 'ArrowLeft') {
        event.preventDefault();
        prevTourStep();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isTourActive, skipTour, nextTourStep, prevTourStep]);

  if (!isTourActive || !currentStep) {
    return null;
  }

  const isLastStep = currentStepIndex === steps.length - 1;
  const isFirstStep = currentStepIndex === 0;

  return (
    <dialog
      open
      aria-modal="true"
      aria-label="功能漫游指引"
      className="fixed inset-0 z-50 overflow-hidden pointer-events-auto bg-transparent border-0 p-0 m-0 w-full h-full max-w-none max-h-none block"
    >
      {/* 半透明遮罩层 */}
      <div className="absolute inset-0 bg-slate-950/70 backdrop-blur-xs transition-opacity duration-300" />

      {/* 聚光灯高亮框 */}
      {rect && (
        <div
          data-testid="spotlight-highlight"
          className="absolute rounded-lg border-2 border-indigo-400 bg-transparent ring-4 ring-indigo-500/20 shadow-2xl transition-all duration-300 pointer-events-none"
          style={{
            top: `${Math.max(0, rect.top - 4)}px`,
            left: `${Math.max(0, rect.left - 4)}px`,
            width: `${rect.width + 8}px`,
            height: `${rect.height + 8}px`,
          }}
        />
      )}

      {/* 指引卡片 */}
      <div
        className="absolute inset-0 flex items-center justify-center p-4 pointer-events-none"
        style={
          rect
            ? {
                top: `${Math.min(window.innerHeight - 260, Math.max(20, rect.top + rect.height + 16))}px`,
                left: `${Math.min(window.innerWidth - 380, Math.max(20, rect.left))}px`,
                alignItems: 'flex-start',
                justifyContent: 'flex-start',
              }
            : undefined
        }
      >
        <div className="pointer-events-auto w-full max-w-sm rounded-xl border border-slate-700 bg-slate-900/95 p-5 shadow-2xl backdrop-blur-md text-slate-100 animate-in fade-in zoom-in-95 duration-200">
          <div className="flex items-center justify-between pb-3 border-b border-slate-800">
            <div className="flex items-center gap-2">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-indigo-500/20 text-indigo-400">
                <Compass className="h-3.5 w-3.5" />
              </span>
              <span className="text-xs font-semibold uppercase tracking-wider text-indigo-400">
                {currentStep.badgeText ?? '功能概览'}
              </span>
              <span className="text-xs text-slate-400">
                {currentStepIndex + 1} / {steps.length}
              </span>
            </div>
            <button
              type="button"
              onClick={skipTour}
              aria-label="跳过引导"
              className="rounded-md p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="py-4">
            <h3 className="text-base font-semibold text-slate-100 flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-amber-400 shrink-0" />
              {currentStep.title}
            </h3>
            <p className="mt-2 text-xs leading-relaxed text-slate-300">
              {currentStep.description}
            </p>
          </div>

          <div className="flex items-center justify-between pt-2">
            <button
              type="button"
              onClick={prevTourStep}
              disabled={isFirstStep}
              className={`flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors ${
                isFirstStep
                  ? 'text-slate-600 cursor-not-allowed'
                  : 'text-slate-300 hover:bg-slate-800 hover:text-white'
              }`}
            >
              <ChevronLeft className="h-3.5 w-3.5" />
              上一步
            </button>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={skipTour}
                className="rounded-lg px-2.5 py-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors"
              >
                跳过全部
              </button>
              <button
                type="button"
                onClick={isLastStep ? finishTour : nextTourStep}
                className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3.5 py-1.5 text-xs font-medium text-white shadow-sm hover:bg-indigo-500 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500 transition-colors"
              >
                {isLastStep ? (
                  <>
                    <Check className="h-3.5 w-3.5" />
                    完成体验
                  </>
                ) : (
                  <>
                    {currentStep.actionLabel ?? '下一步'}
                    <ChevronRight className="h-3.5 w-3.5" />
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      </div>
    </dialog>
  );
};
