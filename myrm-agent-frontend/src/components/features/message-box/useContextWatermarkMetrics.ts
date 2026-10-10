/**
 * [INPUT]
 * - types::Message, ContextBudget (POS: Chat message and context budget domain models.)
 *
 * [OUTPUT]
 * - useContextWatermarkMetrics: hook extracting turn-by-turn token history, delta vs previous turn,
 *   and 4-tier dual-theme weather semantics (<25% clear, 25-75% cloudy, 75-90% warning, >=90% critical).
 * - calculateContextWatermarkMetrics: pure calculation helper for unit testing and non-reactive paths.
 *
 * [POS]
 * Metrics derivation layer for ContextWatermarkUsageGauge and TurnGrowthSparkline.
 */

import { useMemo } from 'react';
import type { Message } from '@/store/useChatStore';
import type { ContextBudget } from '@/store/chat/types';

export type ContextWeatherTier = 'clear' | 'cloudy' | 'warning' | 'critical';

export interface ContextWatermarkMetrics {
  latestBudget: ContextBudget | null;
  historyTurnTokens: number[];
  deltaTokens: number;
  hasDelta: boolean;
  usagePercent: number;
  weatherTier: ContextWeatherTier;
  weatherBadgeClass: string;
  weatherLabelKey: 'weatherClear' | 'weatherCloudy' | 'weatherWarning' | 'weatherCritical';
}

const WEATHER_CLASSES: Record<ContextWeatherTier, string> = {
  clear: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/25',
  cloudy: 'bg-sky-500/10 text-sky-600 dark:text-sky-400 border-sky-500/25',
  warning: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/25',
  critical: 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/25',
};

const WEATHER_LABEL_KEYS: Record<ContextWeatherTier, ContextWatermarkMetrics['weatherLabelKey']> = {
  clear: 'weatherClear',
  cloudy: 'weatherCloudy',
  warning: 'weatherWarning',
  critical: 'weatherCritical',
};

export function resolveWeatherTier(usagePercent: number): ContextWeatherTier {
  if (usagePercent < 25) {
    return 'clear';
  }
  if (usagePercent < 75) {
    return 'cloudy';
  }
  if (usagePercent < 90) {
    return 'warning';
  }
  return 'critical';
}

export function calculateContextWatermarkMetrics(
  messages: readonly Message[],
  maxTurns: number = 12,
): ContextWatermarkMetrics {
  const assistantBudgets: ContextBudget[] = [];

  for (let i = 0; i < messages.length; i++) {
    const msg = messages[i];
    if (msg.role === 'assistant' && msg.contextBudget && msg.contextBudget.current_tokens > 0) {
      assistantBudgets.push(msg.contextBudget);
    }
  }

  if (assistantBudgets.length === 0) {
    return {
      latestBudget: null,
      historyTurnTokens: [],
      deltaTokens: 0,
      hasDelta: false,
      usagePercent: 0,
      weatherTier: 'clear',
      weatherBadgeClass: WEATHER_CLASSES.clear,
      weatherLabelKey: WEATHER_LABEL_KEYS.clear,
    };
  }

  const latestBudget = assistantBudgets[assistantBudgets.length - 1];
  const historySlice = assistantBudgets.slice(-maxTurns);
  const historyTurnTokens = historySlice.map((b) => b.current_tokens);

  const hasDelta = assistantBudgets.length >= 2;
  const prevBudget = hasDelta ? assistantBudgets[assistantBudgets.length - 2] : null;
  const deltaTokens = prevBudget ? latestBudget.current_tokens - prevBudget.current_tokens : 0;

  const usagePercent = Math.min(100, Math.max(0, latestBudget.usage_percent));
  const weatherTier = resolveWeatherTier(usagePercent);

  return {
    latestBudget,
    historyTurnTokens,
    deltaTokens,
    hasDelta,
    usagePercent,
    weatherTier,
    weatherBadgeClass: WEATHER_CLASSES[weatherTier],
    weatherLabelKey: WEATHER_LABEL_KEYS[weatherTier],
  };
}

export function useContextWatermarkMetrics(
  messages: readonly Message[],
  maxTurns: number = 12,
): ContextWatermarkMetrics {
  return useMemo(
    () => calculateContextWatermarkMetrics(messages, maxTurns),
    [messages, maxTurns],
  );
}
