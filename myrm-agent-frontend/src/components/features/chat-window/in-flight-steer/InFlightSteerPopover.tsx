/**
 * [INPUT] ActiveSubagentSwimlane, steer callbacks, preset options
 * [OUTPUT] InFlightSteerPopover (Compact inline steer control and graceful stop modal/popover)
 * [POS] Features -> Chat Window -> In-Flight Steer -> Popover
 */

'use client';

import React, { useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { Compass, StopCircle, Send, X, Sparkles, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import type { ActiveSubagentSwimlane, SteerPresetOption } from './inFlightSteerTypes';
import { useInFlightSteerStore } from './useInFlightSteerStore';

export const STEER_PRESETS: SteerPresetOption[] = [
  { id: 'concise', labelKey: 'presetConciseLabel', instructionKey: 'presetConciseInstruction' },
  { id: 'defensive', labelKey: 'presetDefensiveLabel', instructionKey: 'presetDefensiveInstruction' },
  { id: 'lightweight', labelKey: 'presetLightweightLabel', instructionKey: 'presetLightweightInstruction' },
  { id: 'draft_now', labelKey: 'presetDraftNowLabel', instructionKey: 'presetDraftNowInstruction' },
];

export interface InFlightSteerPopoverProps {
  subagent: ActiveSubagentSwimlane;
  onClose: () => void;
  className?: string;
}

export const InFlightSteerPopover: React.FC<InFlightSteerPopoverProps> = ({
  subagent,
  onClose,
  className,
}) => {
  const t = useTranslations('inFlightSteer');
  const { sendSteerInstruction, stopAndKeepArtifacts, isSteering } = useInFlightSteerStore();
  const [customInstruction, setCustomInstruction] = useState('');

  const handleSendCustom = useCallback(async () => {
    if (!customInstruction.trim() || isSteering) {
      return;
    }
    const success = await sendSteerInstruction(subagent.id, customInstruction.trim());
    if (success) {
      setCustomInstruction('');
      onClose();
    }
  }, [customInstruction, isSteering, sendSteerInstruction, subagent.id, onClose]);

  const handleSelectPreset = useCallback(
    async (instruction: string) => {
      if (isSteering) {
        return;
      }
      const success = await sendSteerInstruction(subagent.id, instruction);
      if (success) {
        onClose();
      }
    },
    [isSteering, sendSteerInstruction, subagent.id, onClose],
  );

  const handleStopGracefully = useCallback(async () => {
    if (isSteering) {
      return;
    }
    const success = await stopAndKeepArtifacts(subagent.id);
    if (success) {
      onClose();
    }
  }, [isSteering, stopAndKeepArtifacts, subagent.id, onClose]);

  return (
    <dialog
      open
      aria-modal="true"
      aria-label={t('steerSubagentAria', { name: subagent.name })}
      className={cn(
        'w-80 p-4 m-0 rounded-xl shadow-xl border bg-white dark:bg-neutral-900 border-neutral-200 dark:border-neutral-800 text-neutral-900 dark:text-neutral-100 z-50 animate-in fade-in zoom-in-95 duration-150',
        className,
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-neutral-100 dark:border-neutral-800">
        <div className="flex items-center gap-2">
          <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-indigo-500/10 text-indigo-600 dark:text-indigo-400">
            <Compass size={16} />
          </div>
          <div>
            <h4 className="text-xs font-semibold leading-tight">{subagent.name}</h4>
            <p className="text-[10px] text-neutral-400 leading-tight truncate max-w-[170px]">
              {subagent.role} · {subagent.currentStep}
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="p-1 rounded-md text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
          aria-label={t('close')}
        >
          <X size={14} />
        </button>
      </div>

      {/* Preset Pills */}
      <div className="mt-3">
        <div className="flex items-center gap-1 text-[11px] font-medium text-neutral-500 dark:text-neutral-400 mb-1.5">
          <Sparkles size={12} className="text-amber-500" />
          <span>{t('quickPresets')}</span>
        </div>
        <div className="grid grid-cols-2 gap-1.5">
          {STEER_PRESETS.map((preset) => (
            <button
              key={preset.id}
              type="button"
              disabled={isSteering}
              onClick={() => handleSelectPreset(t(preset.instructionKey))}
              className="text-left px-2.5 py-1.5 rounded-lg text-xs border border-neutral-200 dark:border-neutral-700 hover:border-indigo-500 dark:hover:border-indigo-400 hover:bg-indigo-50/50 dark:hover:bg-indigo-950/30 transition-colors disabled:opacity-50"
              title={t(preset.instructionKey)}
            >
              <span className="font-medium">{t(preset.labelKey)}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Custom Input */}
      <div className="mt-3">
        <div className="flex gap-1.5">
          <input
            type="text"
            value={customInstruction}
            onChange={(e) => setCustomInstruction(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                handleSendCustom();
              }
            }}
            placeholder={t('inputPlaceholder')}
            disabled={isSteering}
            className="flex-1 px-2.5 py-1.5 text-xs rounded-lg border border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
          <button
            type="button"
            disabled={!customInstruction.trim() || isSteering}
            onClick={handleSendCustom}
            className="px-2.5 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-medium inline-flex items-center gap-1 transition-colors disabled:opacity-40"
            aria-label={t('sendInstructionAria')}
          >
            {isSteering ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />}
          </button>
        </div>
      </div>

      {/* Graceful Early-Stop Action */}
      <div className="mt-3 pt-3 border-t border-neutral-100 dark:border-neutral-800">
        <button
          type="button"
          disabled={isSteering}
          onClick={handleStopGracefully}
          className="w-full inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/30 hover:bg-red-100 dark:hover:bg-red-900/40 border border-red-200 dark:border-red-900/40 transition-colors disabled:opacity-50"
        >
          <StopCircle size={13} />
          <span>{t('stopEarly')}</span>
        </button>
      </div>
    </dialog>
  );
};

InFlightSteerPopover.displayName = 'InFlightSteerPopover';
