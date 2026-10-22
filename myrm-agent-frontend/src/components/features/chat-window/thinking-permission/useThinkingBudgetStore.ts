/**
 * [INPUT]
 * - thinkingPermissionTypes::ThinkingEffortLevel, THINKING_BUDGET_TIERS (POS: Budget tiers contract.)
 * - message-input-actions/ThinkingIntensityButton::setGlobalIntensity (POS: Sync with legacy intensity bus.)
 * - zustand::create (POS: Reactive state management.)
 *
 * [OUTPUT]
 * - useThinkingBudgetStore: hook providing reactive thinking effort level and token budget.
 *
 * [POS]
 * Central reactive store for model reasoning effort budget, supporting smooth sliding,
 * persistence by model slug, and automatic parameter binding.
 */

import { create } from 'zustand';
import {
  type ThinkingEffortLevel,
  THINKING_BUDGET_TIERS,
} from './thinkingPermissionTypes';
import { setGlobalIntensity } from '@/components/features/message-input-actions/ThinkingIntensityButton';

const STORAGE_PREFIX = 'myrm_thinking_budget_';

interface ThinkingBudgetState {
  level: ThinkingEffortLevel;
  currentModel: string;
  tokenBudget: number;
  reasoningEffort?: 'low' | 'medium' | 'high';
  setLevel: (level: ThinkingEffortLevel, modelName?: string) => void;
  hydrateForModel: (modelName: string) => void;
}

function resolveTierConfig(level: ThinkingEffortLevel) {
  const found = THINKING_BUDGET_TIERS.find((t) => t.level === level);
  return found ?? THINKING_BUDGET_TIERS[0];
}

function getStoredLevel(modelName: string): ThinkingEffortLevel {
  if (typeof window === 'undefined' || !modelName) {
    return 'off';
  }
  try {
    const raw = localStorage.getItem(`${STORAGE_PREFIX}${modelName}`);
    if (raw && ['off', 'low', 'medium', 'high', 'max'].includes(raw)) {
      return raw as ThinkingEffortLevel;
    }
  } catch {
    // Ignore localStorage access failure
  }
  return 'off';
}

function persistLevel(modelName: string, level: ThinkingEffortLevel): void {
  if (typeof window === 'undefined' || !modelName) {
    return;
  }
  try {
    if (level === 'off') {
      localStorage.removeItem(`${STORAGE_PREFIX}${modelName}`);
    } else {
      localStorage.setItem(`${STORAGE_PREFIX}${modelName}`, level);
    }
  } catch {
    // Ignore localStorage access failure
  }
}

export const useThinkingBudgetStore = create<ThinkingBudgetState>((set, get) => ({
  level: 'off',
  currentModel: '',
  tokenBudget: 0,
  reasoningEffort: undefined,

  setLevel: (level: ThinkingEffortLevel, modelName?: string) => {
    const targetModel = modelName ?? get().currentModel;
    const tier = resolveTierConfig(level);

    if (targetModel) {
      persistLevel(targetModel, level);
    }

    // Sync downstream legacy intensity bus so getThinkingEffort() picks it up immediately
    setGlobalIntensity(level, targetModel);

    set({
      level,
      tokenBudget: tier.tokenBudget,
      reasoningEffort: tier.reasoningEffort,
    });
  },

  hydrateForModel: (modelName: string) => {
    if (!modelName || modelName === get().currentModel) {
      return;
    }
    const stored = getStoredLevel(modelName);
    const tier = resolveTierConfig(stored);

    // Sync legacy intensity bus
    setGlobalIntensity(stored, modelName);

    set({
      currentModel: modelName,
      level: stored,
      tokenBudget: tier.tokenBudget,
      reasoningEffort: tier.reasoningEffort,
    });
  },
}));
