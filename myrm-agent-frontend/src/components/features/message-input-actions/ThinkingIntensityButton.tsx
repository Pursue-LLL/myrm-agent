'use client';

/**
 * [INPUT]
 * - @/store/useProviderStore::useProviderStore (POS: Provider and default model configuration store)
 * - @/lib/model-binding::resolveActiveModelSelection (POS: Resolves the model a mode or agent binds)
 * - @/lib/reasoning-model-detection::detectReasoningSupport (POS: Whether a model can reason)
 * - @/hooks/ui/persistedStringStore::createPersistedStringStore (POS: Per-device key-to-string memory that survives reloads)
 *
 * [OUTPUT]
 * - ThinkingIntensityButton (default): composer picker for the thinking intensity of the active model.
 * - IntensityLevel, INTENSITY_OPTIONS: the selectable levels (auto, off, low, medium, high, xhigh, max).
 * - setGlobalIntensity, setGlobalCustomValue, getThinkingEffort, useGlobalIntensity: the module-level intensity state
 *   shared with the thinking-budget store, the mobile sheet and the request builder; getThinkingEffort is what a request
 *   carries (a custom value when set, else the level, undefined on auto).
 *
 * [POS]
 * Thinking-intensity picker and the intensity state behind it. `auto` (default) asks nothing of the model and is not
 * saved; `off`, another level or a custom value is saved per model on this device and restored when the model comes back.
 */

import { useState, useCallback, useEffect, useMemo, useRef, useSyncExternalStore } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';
import useProviderStore from '@/store/useProviderStore';
import { useShallow } from 'zustand/react/shallow';
import { createPersistedStringStore } from '@/hooks/ui/persistedStringStore';
import { resolveActiveModelSelection } from '@/lib/model-binding';
import { detectReasoningSupport } from '@/lib/reasoning-model-detection';
import { isImeComposing } from '@/lib/utils/imeUtils';
import type { ActionMode, AgentConfig } from '@/store/chat/types';

/**
 * `auto` asks for nothing: the model keeps its own default depth (and any default configured on the model).
 * `off` asks for no thinking. The other levels ask for that depth.
 */
export type IntensityLevel = 'auto' | 'off' | 'low' | 'medium' | 'high' | 'xhigh' | 'max';

export interface IntensityOption {
  value: IntensityLevel;
  labelKey: string;
  color: string;
  activeColor: string;
}

export const INTENSITY_OPTIONS: IntensityOption[] = [
  { value: 'auto', labelKey: 'auto', color: 'bg-primary/50', activeColor: 'text-muted-foreground' },
  { value: 'off', labelKey: 'off', color: 'bg-slate-400', activeColor: 'text-slate-500 dark:text-slate-400' },
  { value: 'low', labelKey: 'low', color: 'bg-sky-400', activeColor: 'text-sky-500 dark:text-sky-400' },
  { value: 'medium', labelKey: 'medium', color: 'bg-amber-400', activeColor: 'text-amber-500 dark:text-amber-400' },
  { value: 'high', labelKey: 'high', color: 'bg-orange-500', activeColor: 'text-orange-500 dark:text-orange-400' },
  { value: 'xhigh', labelKey: 'xhigh', color: 'bg-red-500', activeColor: 'text-red-500 dark:text-red-400' },
  { value: 'max', labelKey: 'max', color: 'bg-rose-500', activeColor: 'text-rose-500 dark:text-rose-400' },
];

const STORAGE_PREFIX = 'thinkingIntensity_';
const CUSTOM_STORAGE_PREFIX = 'thinkingIntensityCustom_';
const DEFAULT_INTENSITY: IntensityLevel = 'auto';

interface StoredIntensity {
  intensity: IntensityLevel;
  customValue: string;
}

// A browser that refuses storage keeps each model's choice for the page instead of dropping it.
const savedLevels = createPersistedStringStore(STORAGE_PREFIX);
const savedCustomValues = createPersistedStringStore(CUSTOM_STORAGE_PREFIX);

function getStoredIntensity(modelName: string): StoredIntensity | null {
  const customStored = savedCustomValues.read(modelName);
  if (customStored) {
    return { intensity: DEFAULT_INTENSITY, customValue: customStored };
  }
  const stored = savedLevels.read(modelName);
  if (stored && INTENSITY_OPTIONS.some((o) => o.value === stored)) {
    return { intensity: stored as IntensityLevel, customValue: '' };
  }
  return null;
}

function storeIntensity(modelName: string, level: IntensityLevel): void {
  savedCustomValues.remove(modelName);
  if (level === DEFAULT_INTENSITY) {
    savedLevels.remove(modelName);
  } else {
    savedLevels.write(modelName, level);
  }
}

function storeCustomValue(modelName: string, value: string): void {
  savedLevels.remove(modelName);
  if (value) {
    savedCustomValues.write(modelName, value);
  } else {
    savedCustomValues.remove(modelName);
  }
}

function intensityToReasoningEffort(level: IntensityLevel): string | undefined {
  return level === 'auto' ? undefined : level;
}

const ThinkingIcon = ({ className, intensity }: { className?: string; intensity: IntensityLevel }) => {
  const option = INTENSITY_OPTIONS.find((o) => o.value === intensity);
  const isActive = intensity !== 'auto' && intensity !== 'off';

  return (
    <svg
      aria-hidden="true"
      xmlns="http://www.w3.org/2000/svg"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cn(
        'shrink-0 transition-all duration-300',
        isActive ? option?.activeColor : 'text-muted-foreground',
        className,
      )}
    >
      <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z" strokeWidth="1.2" opacity={0.4} />
      <path d="M12 6v2M12 16v2M6 12h2M16 12h2" />
      <circle cx="12" cy="12" r="3" fill={isActive ? 'currentColor' : 'none'} strokeWidth={isActive ? 0 : 1.5} />
    </svg>
  );
};

interface IntensityState {
  intensity: IntensityLevel;
  customValue: string;
}

let _state: IntensityState = { intensity: DEFAULT_INTENSITY, customValue: '' };
const _listeners = new Set<() => void>();

function _notify() {
  _listeners.forEach((fn) => fn());
}

export function setGlobalIntensity(level: IntensityLevel, modelName?: string) {
  if (_state.intensity === level && _state.customValue === '') {
    return;
  }
  _state = { intensity: level, customValue: '' };
  if (modelName) {
    storeIntensity(modelName, level);
  }
  _notify();
}

export function setGlobalCustomValue(value: string, modelName?: string) {
  if (_state.customValue === value && _state.intensity === DEFAULT_INTENSITY) {
    return;
  }
  _state = { intensity: DEFAULT_INTENSITY, customValue: value };
  if (modelName) {
    storeCustomValue(modelName, value);
  }
  _notify();
}

export function getThinkingEffort(): string | undefined {
  if (_state.customValue) {
    return _state.customValue;
  }
  return intensityToReasoningEffort(_state.intensity);
}

function _subscribe(listener: () => void) {
  _listeners.add(listener);
  return () => {
    _listeners.delete(listener);
  };
}

function _getSnapshot(): IntensityState {
  return _state;
}

export function useGlobalIntensity(): IntensityState {
  return useSyncExternalStore(_subscribe, _getSnapshot, _getSnapshot);
}

interface ThinkingIntensityButtonProps {
  actionMode: ActionMode;
  agentConfig: AgentConfig | null;
}

const ThinkingIntensityButton = ({ actionMode, agentConfig }: ThinkingIntensityButtonProps) => {
  const t = useTranslations('thinkingIntensity');
  const [open, setOpen] = useState(false);
  const [showCustomInput, setShowCustomInput] = useState(false);
  const [customInputValue, setCustomInputValue] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const { intensity, customValue } = useGlobalIntensity();

  const { defaultModelConfig, providers, customModelInfo } = useProviderStore(
    useShallow((s) => ({
      defaultModelConfig: s.defaultModelConfig,
      providers: s.providers,
      customModelInfo: s.customModelInfo,
    })),
  );

  const currentModel = useMemo(() => {
    const selection = resolveActiveModelSelection(actionMode, agentConfig, defaultModelConfig, providers);
    if (!selection) {
      return null;
    }
    const key = `${selection.providerId}/${selection.model}`;
    const info = customModelInfo[key];
    return {
      name: selection.model,
      supportsReasoning: detectReasoningSupport(selection.model, info?.supports_reasoning),
    };
  }, [actionMode, agentConfig, defaultModelConfig, providers, customModelInfo]);

  const modelName = currentModel?.name ?? '';
  const syncedModelRef = useRef('');

  useEffect(() => {
    if (!modelName || modelName === syncedModelRef.current) {
      return;
    }
    syncedModelRef.current = modelName;
    const stored = getStoredIntensity(modelName);
    if (stored) {
      if (stored.customValue) {
        setGlobalCustomValue(stored.customValue);
      } else {
        setGlobalIntensity(stored.intensity, undefined);
      }
    } else {
      setGlobalIntensity(DEFAULT_INTENSITY, undefined);
    }
  }, [modelName]);

  const handleSelect = useCallback(
    (level: IntensityLevel) => {
      setGlobalIntensity(level, currentModel?.name);
      setShowCustomInput(false);
      setOpen(false);
    },
    [currentModel?.name],
  );

  const handleCustomSubmit = useCallback(() => {
    const trimmed = customInputValue.trim();
    if (!trimmed) {
      return;
    }
    setGlobalCustomValue(trimmed, currentModel?.name);
    setShowCustomInput(false);
    setOpen(false);
  }, [customInputValue, currentModel?.name]);

  useEffect(() => {
    if (showCustomInput && inputRef.current) {
      inputRef.current.focus();
    }
  }, [showCustomInput]);

  if (!currentModel?.supportsReasoning) {
    return null;
  }

  const activeOption = INTENSITY_OPTIONS.find((o) => o.value === intensity);
  const isDefaultChoice = intensity === DEFAULT_INTENSITY && !customValue;
  const displayLabel = customValue || (intensity !== DEFAULT_INTENSITY ? t(activeOption?.labelKey ?? 'off') : null);

  return (
    <TooltipProvider delayDuration={200}>
      <Popover open={open} onOpenChange={setOpen}>
        <Tooltip>
          <TooltipTrigger asChild>
            <PopoverTrigger asChild>
              <button
                type="button"
                aria-label={displayLabel ? `${t('title')}: ${displayLabel}` : t('title')}
                className={cn(
                  'group relative flex items-center gap-1 px-2 h-8 rounded-lg transition-all duration-200',
                  'hover:bg-black/[0.06] dark:hover:bg-white/[0.08]',
                  isDefaultChoice ? '' : 'bg-black/[0.04] dark:bg-white/[0.06]',
                )}
              >
                <ThinkingIcon intensity={customValue ? 'high' : intensity} />
                {displayLabel && (
                  <span
                    className={cn(
                      'text-xs font-medium max-w-[60px] truncate',
                      customValue ? 'text-orange-500 dark:text-orange-400' : activeOption?.activeColor,
                    )}
                  >
                    {displayLabel}
                  </span>
                )}
              </button>
            </PopoverTrigger>
          </TooltipTrigger>
          <TooltipContent side="top">
            <p className="font-medium text-sm">{t('title')}</p>
            <p className="text-xs text-muted-foreground mt-0.5">{t('description')}</p>
          </TooltipContent>
        </Tooltip>

        <PopoverContent side="top" align="start" className="w-56 p-2">
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground px-2 pb-1">{t('title')}</p>

            {INTENSITY_OPTIONS.map((option) => {
              const isSelected = intensity === option.value && !customValue;
              return (
                <button
                  key={option.value}
                  type="button"
                  aria-pressed={isSelected}
                  onClick={() => handleSelect(option.value)}
                  className={cn(
                    'w-full flex items-center gap-2.5 px-2 py-1.5 rounded-full text-sm transition-colors',
                    isSelected ? 'bg-primary/10 dark:bg-primary/15' : 'hover:bg-muted/80',
                  )}
                >
                  <span className={cn('w-2 h-2 rounded-full shrink-0', option.color)} />
                  <span className={cn('font-medium', isSelected ? 'text-foreground' : 'text-muted-foreground')}>
                    {t(option.labelKey)}
                  </span>
                  {option.value === DEFAULT_INTENSITY && (
                    <span className="text-xs text-muted-foreground/70 ml-auto">{t('default')}</span>
                  )}
                </button>
              );
            })}

            <div className="border-t border-border my-1" />

            {showCustomInput ? (
              <div className="flex items-center gap-1.5 px-1">
                <input
                  ref={inputRef}
                  type="text"
                  aria-label={t('custom')}
                  value={customInputValue}
                  onChange={(e) => setCustomInputValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (isImeComposing(e)) {
                      return;
                    }
                    if (e.key === 'Enter') {
                      handleCustomSubmit();
                    }
                    if (e.key === 'Escape') {
                      setShowCustomInput(false);
                    }
                  }}
                  placeholder={t('customPlaceholder')}
                  className="flex-1 h-7 px-2 text-xs bg-muted rounded border border-border focus:outline-none focus:border-primary"
                />
                <button
                  type="button"
                  onClick={handleCustomSubmit}
                  disabled={!customInputValue.trim()}
                  className="h-7 px-2 text-xs font-medium text-primary hover:bg-primary/10 rounded disabled:opacity-40 transition-colors"
                >
                  {t('apply')}
                </button>
              </div>
            ) : (
              <button
                type="button"
                aria-pressed={Boolean(customValue)}
                onClick={() => {
                  setShowCustomInput(true);
                  setCustomInputValue(customValue || '');
                }}
                className={cn(
                  'w-full flex items-center gap-2.5 px-2 py-1.5 rounded-full text-sm transition-colors',
                  customValue ? 'bg-primary/10 dark:bg-primary/15' : 'hover:bg-muted/80',
                )}
              >
                <span className="w-2 h-2 rounded-full shrink-0 border border-dashed border-muted-foreground/50" />
                <span className={cn('font-medium', customValue ? 'text-foreground' : 'text-muted-foreground')}>
                  {customValue ? customValue : t('custom')}
                </span>
              </button>
            )}
          </div>
        </PopoverContent>
      </Popover>
    </TooltipProvider>
  );
};

export default ThinkingIntensityButton;
