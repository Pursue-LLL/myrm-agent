'use client';

/**
 * MemorySecondaryGovernanceToolbar Component.
 * In-place secondary governance toolbar for single memory candidates:
 * confidence weight slider, negative pitfall toggle, lifecycle status locking, and deduplication merge.
 * Adheres strictly to zero-emoji and explicit type constraints.
 */

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import { AlertOctagon, Check, CheckCircle2, GitMerge, Lock, Sliders, Unlock, XCircle } from 'lucide-react';
import { promptText } from '@/lib/app-dialog';
import { MemoryLifecycleStatus, RecallCandidate } from './recallSimulatorTypes';

interface MemorySecondaryGovernanceToolbarProps {
  candidate: RecallCandidate;
  onUpdate: (updated: Partial<RecallCandidate>, mergedIntoId?: string) => Promise<void>;
}

export const MemorySecondaryGovernanceToolbar: React.FC<MemorySecondaryGovernanceToolbarProps> = ({
  candidate,
  onUpdate,
}) => {
  let t = (key: string): string => key;
  try {
    const translation = useTranslations('memoryRecall');
    t = (key: string): string => translation(key);
  } catch {
    // Fallback in test suites
  }

  const [confidence, setConfidence] = useState<number>(candidate.confidence);
  const [isNegativeTrap, setIsNegativeTrap] = useState<boolean>(candidate.is_negative_trap);
  const [status, setStatus] = useState<MemoryLifecycleStatus>(candidate.status);
  const [isUpdating, setIsUpdating] = useState<boolean>(false);
  const [isSuccessFeedback, setIsSuccessFeedback] = useState<boolean>(false);

  const handleConfidenceChange = (e: React.ChangeEvent<HTMLInputElement>): void => {
    const val = parseFloat(e.target.value);
    setConfidence(val);
  };

  const handleConfidenceCommit = async (): Promise<void> => {
    if (confidence === candidate.confidence) {
      return;
    }
    setIsUpdating(true);
    try {
      await onUpdate({ confidence });
      showSuccessIndicator();
    } finally {
      setIsUpdating(false);
    }
  };

  const handleToggleNegativeTrap = async (): Promise<void> => {
    const nextState = !isNegativeTrap;
    setIsNegativeTrap(nextState);
    setIsUpdating(true);
    try {
      await onUpdate({ is_negative_trap: nextState });
      showSuccessIndicator();
    } finally {
      setIsUpdating(false);
    }
  };

  const handleToggleLockStatus = async (): Promise<void> => {
    const nextStatus: MemoryLifecycleStatus = status === 'locked' ? 'active' : 'locked';
    setStatus(nextStatus);
    setIsUpdating(true);
    try {
      await onUpdate({ status: nextStatus });
      showSuccessIndicator();
    } finally {
      setIsUpdating(false);
    }
  };

  const handleToggleDisableStatus = async (): Promise<void> => {
    const nextStatus: MemoryLifecycleStatus = status === 'disabled' ? 'active' : 'disabled';
    setStatus(nextStatus);
    setIsUpdating(true);
    try {
      await onUpdate({ status: nextStatus });
      showSuccessIndicator();
    } finally {
      setIsUpdating(false);
    }
  };

  const handleMergeDuplicate = async (): Promise<void> => {
    const targetId = (await promptText({ title: t('mergeDuplicateBtn'), description: t('mergePrompt') }))?.trim();
    if (!targetId) {
      return;
    }
    setIsUpdating(true);
    try {
      await onUpdate({ status: 'disabled' }, targetId);
      showSuccessIndicator();
    } finally {
      setIsUpdating(false);
    }
  };

  const showSuccessIndicator = (): void => {
    setIsSuccessFeedback(true);
    setTimeout(() => {
      setIsSuccessFeedback(false);
    }, 1500);
  };

  const isLocked = status === 'locked';
  const isDisabled = status === 'disabled';

  return (
    <div className="p-3 rounded-xl bg-slate-950/80 border border-slate-800 flex flex-wrap items-center justify-between gap-3 text-xs">
      {/* Confidence Weight Slider */}
      <div className="flex items-center gap-2.5 min-w-[200px] flex-1">
        <Sliders className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
        <label
          htmlFor={`confidence-slider-${candidate.memory_id}`}
          className="text-slate-400 text-[11px] whitespace-nowrap"
        >
          {t('confidenceWeight')}:
        </label>
        <input
          id={`confidence-slider-${candidate.memory_id}`}
          type="range"
          min="0.0"
          max="1.0"
          step="0.05"
          value={confidence}
          onChange={handleConfidenceChange}
          onMouseUp={handleConfidenceCommit}
          onTouchEnd={handleConfidenceCommit}
          className="w-24 sm:w-32 h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-indigo-500"
        />
        <span className="font-mono text-indigo-300 font-semibold text-[11px] w-10 text-right">
          {(confidence * 100).toFixed(0)}%
        </span>
      </div>

      {/* Governance Action Buttons */}
      <div className="flex items-center gap-2 shrink-0">
        {/* Negative Pitfall Toggle */}
        <button
          type="button"
          onClick={handleToggleNegativeTrap}
          disabled={isUpdating}
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-[11px] font-medium transition-all ${
            isNegativeTrap
              ? 'bg-rose-500/15 border-rose-500/40 text-rose-300 shadow-sm'
              : 'bg-slate-900 border-slate-800 text-slate-400 hover:text-slate-300'
          }`}
        >
          <AlertOctagon className="w-3 h-3 text-rose-400" />
          <span>{isNegativeTrap ? t('mustAvoidTrap') : t('normalGene')}</span>
        </button>

        {/* Lock/Unlock Button */}
        <button
          type="button"
          onClick={handleToggleLockStatus}
          disabled={isUpdating}
          className={`p-1.5 rounded-lg border text-[11px] transition-colors ${
            isLocked
              ? 'bg-amber-500/15 border-amber-500/30 text-amber-300'
              : 'bg-slate-900 border-slate-800 text-slate-400 hover:text-slate-200'
          }`}
          title={isLocked ? t('unlockBtn') : t('lockBtn')}
          aria-label={isLocked ? t('unlockBtn') : t('lockBtn')}
        >
          {isLocked ? <Lock className="w-3.5 h-3.5" /> : <Unlock className="w-3.5 h-3.5" />}
        </button>

        {/* Disable/Enable Button */}
        <button
          type="button"
          onClick={handleToggleDisableStatus}
          disabled={isUpdating}
          className={`p-1.5 rounded-lg border text-[11px] transition-colors ${
            isDisabled
              ? 'bg-red-500/15 border-red-500/30 text-red-300'
              : 'bg-slate-900 border-slate-800 text-slate-400 hover:text-slate-200'
          }`}
          title={isDisabled ? t('enableBtn') : t('disableBtn')}
          aria-label={isDisabled ? t('enableBtn') : t('disableBtn')}
        >
          {isDisabled ? (
            <XCircle className="w-3.5 h-3.5 text-red-400" />
          ) : (
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
          )}
        </button>

        {/* Merge Duplicate Button */}
        <button
          type="button"
          onClick={handleMergeDuplicate}
          disabled={isUpdating}
          className="flex items-center gap-1 px-2 py-1 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-400 hover:text-indigo-300 text-[11px] transition-colors"
          title={t('mergeDuplicateBtn')}
        >
          <GitMerge className="w-3 h-3" />
          <span className="hidden sm:inline">{t('mergeDuplicateBtn')}</span>
        </button>

        {/* Success Feedback Pulse */}
        {isSuccessFeedback && (
          <span className="flex items-center gap-1 text-[11px] text-emerald-400 font-medium animate-in fade-in duration-100">
            <Check className="w-3 h-3" />
          </span>
        )}
      </div>
    </div>
  );
};
