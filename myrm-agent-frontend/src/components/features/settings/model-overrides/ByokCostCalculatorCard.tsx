/**
 * BYOK Token Economics & Live Cost Calculator Card.
 *
 * Provides real-time calculation of run costs based on prompt
 * input and completion output tokens.
 */

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import { Calculator } from 'lucide-react';

import type { CostEstimationResponse } from './modelOverridesTypes';
import { ModelOverridesService } from './modelOverridesService';

export interface ByokCostCalculatorCardProps {
  modelId: string;
  className?: string;
}

export const ByokCostCalculatorCard: React.FC<ByokCostCalculatorCardProps> = ({
  modelId,
  className = '',
}) => {
  let t: (key: string, fallback?: string) => string;
  try {
    const intlT = useTranslations('modelOverrides');
    t = (key: string, fallback?: string) => {
      try {
        const val = intlT(key);
        return val || (fallback ?? key);
      } catch {
        return fallback ?? key;
      }
    };
  } catch {
    t = (_key: string, fallback?: string) => fallback ?? _key;
  }

  const [calcInputTokens, setCalcInputTokens] = useState<number>(100000);
  const [calcOutputTokens, setCalcOutputTokens] = useState<number>(20000);
  const [calcResult, setCalcResult] = useState<CostEstimationResponse | null>(null);
  const [isCalculating, setIsCalculating] = useState<boolean>(false);

  const handleCalculateCost = async (): Promise<void> => {
    setIsCalculating(true);
    try {
      const res = await ModelOverridesService.estimateCost({
        model_id: modelId,
        input_tokens: calcInputTokens,
        output_tokens: calcOutputTokens,
      });
      setCalcResult(res);
    } finally {
      setIsCalculating(false);
    }
  };

  return (
    <div
      data-testid="byok-cost-calculator-card"
      className={`rounded-xl border border-indigo-100 bg-indigo-50/40 p-4 dark:border-indigo-950/60 dark:bg-indigo-950/20 ${className}`}
    >
      <div className="flex items-center gap-2 mb-3">
        <Calculator className="h-4 w-4 text-indigo-600 dark:text-indigo-400" />
        <h3 className="text-xs font-semibold text-slate-800 dark:text-slate-100">
          {t('calcTitle', 'BYOK 实时用量与成本计算器')}
        </h3>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div>
          <label className="mb-1 block text-xs text-slate-600 dark:text-slate-400">
            {t('calcInputTokens', '预估输入 Tokens')}
          </label>
          <input
            type="number"
            value={calcInputTokens}
            onChange={(e) => {
              setCalcInputTokens(Number(e.target.value));
            }}
            data-testid="calc-input-tokens"
            className="w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-800 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs text-slate-600 dark:text-slate-400">
            {t('calcOutputTokens', '预估输出 Tokens')}
          </label>
          <input
            type="number"
            value={calcOutputTokens}
            onChange={(e) => {
              setCalcOutputTokens(Number(e.target.value));
            }}
            data-testid="calc-output-tokens"
            className="w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-800 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
          />
        </div>
        <div className="flex items-end">
          <button
            type="button"
            disabled={isCalculating}
            onClick={() => {
              void handleCalculateCost();
            }}
            data-testid="calc-estimate-btn"
            className="w-full rounded-lg bg-indigo-600 py-1.5 text-xs font-medium text-white transition hover:bg-indigo-700 disabled:opacity-50"
          >
            {t('calcComputeBtn', '计算单次费用')}
          </button>
        </div>
      </div>

      {calcResult && (
        <div
          data-testid="calc-result-panel"
          className="mt-3 flex items-center justify-between rounded-lg bg-white/80 p-2.5 text-xs text-slate-700 dark:bg-slate-900/80 dark:text-slate-200"
        >
          <div>
            <span>输入: </span>
            <strong>{calcResult.currency === 'USD' ? '$' : '¥'}{calcResult.input_cost}</strong>
            <span className="mx-2">|</span>
            <span>输出: </span>
            <strong>{calcResult.currency === 'USD' ? '$' : '¥'}{calcResult.output_cost}</strong>
          </div>
          <div>
            <span>合计: </span>
            <strong className="text-indigo-600 dark:text-indigo-400 text-sm">
              {calcResult.currency === 'USD' ? '$' : '¥'}{calcResult.total_cost}
            </strong>
          </div>
        </div>
      )}
    </div>
  );
};
