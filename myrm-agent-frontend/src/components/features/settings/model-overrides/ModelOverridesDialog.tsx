/**
 * Model Overrides & BYOK Pricing Manager Dialog.
 *
 * Implements Hermes Agent v0.21.0 model_overrides parity.
 * Empowers users to independently customize context windows, max output limits,
 * and input/output token pricing matrices with a live BYOK cost calculator.
 */

import React, { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  Check,
  ShieldCheck,
  Sliders,
  Sparkles,
  Trash2,
  X,
  Zap,
} from 'lucide-react';

import type {
  CurrencyType,
  ModelOverrideItem,
  PreloadedModelSku,
} from './modelOverridesTypes';
import {
  FALLBACK_PRELOADED_SKUS,
  ModelOverridesService,
} from './modelOverridesService';
import { ByokCostCalculatorCard } from './ByokCostCalculatorCard';

export interface ModelOverridesDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSaved?: (item: ModelOverrideItem) => void;
}

export const ModelOverridesDialog: React.FC<ModelOverridesDialogProps> = ({
  isOpen,
  onClose,
  onSaved,
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

  const [overrides, setOverrides] = useState<ModelOverrideItem[]>([]);
  const [preloadedSkus, setPreloadedSkus] = useState<PreloadedModelSku[]>([...FALLBACK_PRELOADED_SKUS]);
  const [selectedModelId, setSelectedModelId] = useState<string>('glm-5.3-flash');
  const [contextWindow, setContextWindow] = useState<number>(1000000);
  const [maxOutput, setMaxOutput] = useState<number>(8192);
  const [inputPrice, setInputPrice] = useState<number>(0.1);
  const [outputPrice, setOutputPrice] = useState<number>(0.1);
  const [currency, setCurrency] = useState<CurrencyType>('USD');
  const [remarks, setRemarks] = useState<string>('Custom BYOK override');
  const [isSaving, setIsSaving] = useState<boolean>(false);

  useEffect(() => {
    if (isOpen) {
      void loadData();
    }
  }, [isOpen]);

  const loadData = async (): Promise<void> => {
    const [fetchedOverrides, fetchedSkus] = await Promise.all([
      ModelOverridesService.listOverrides(),
      ModelOverridesService.getPreloadedSkus(),
    ]);
    setOverrides(fetchedOverrides);
    setPreloadedSkus(fetchedSkus);

    if (fetchedOverrides.length > 0) {
      applyModelToForm(fetchedOverrides[0]);
    } else if (fetchedSkus.length > 0) {
      applySkuToForm(fetchedSkus[0]);
    }
  };

  const applySkuToForm = (sku: PreloadedModelSku): void => {
    setSelectedModelId(sku.model_id);
    setContextWindow(sku.default_context_window);
    setMaxOutput(sku.default_max_output_tokens);
    setInputPrice(sku.suggested_input_cost_per_mtoken);
    setOutputPrice(sku.suggested_output_cost_per_mtoken);
    setCurrency(sku.currency);
    setRemarks(`Cloned from ${sku.display_name}`);
  };

  const applyModelToForm = (item: ModelOverrideItem): void => {
    setSelectedModelId(item.model_id);
    setContextWindow(item.custom_context_window ?? 128000);
    setMaxOutput(item.custom_max_output_tokens ?? 8192);
    setInputPrice(item.input_cost_per_mtoken ?? 0.1);
    setOutputPrice(item.output_cost_per_mtoken ?? 0.2);
    setCurrency(item.currency);
    setRemarks(item.remarks ?? '');
  };

  const handleSave = async (): Promise<void> => {
    setIsSaving(true);
    try {
      const saved = await ModelOverridesService.upsertOverride(selectedModelId, {
        custom_context_window: contextWindow,
        custom_max_output_tokens: maxOutput,
        input_cost_per_mtoken: inputPrice,
        output_cost_per_mtoken: outputPrice,
        currency,
        enabled: true,
        remarks,
      });

      setOverrides((prev) => {
        const next = prev.filter((i) => i.model_id !== saved.model_id);
        return [...next, saved];
      });

      if (onSaved) {
        onSaved(saved);
      }
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async (modelId: string): Promise<void> => {
    await ModelOverridesService.deleteOverride(modelId);
    setOverrides((prev) => prev.filter((i) => i.model_id !== modelId));
  };

  if (!isOpen) {
    return null;
  }

  return (
    <dialog
      open
      aria-modal="true"
      data-testid="model-overrides-dialog"
      className="fixed inset-0 z-50 m-0 flex h-full w-full max-h-none max-w-none items-center justify-center bg-slate-900/60 p-4 backdrop-blur-sm"
    >
      <div className="flex max-h-[92vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl dark:border-slate-800 dark:bg-slate-900">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4 dark:border-slate-800">
          <div className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600 dark:bg-indigo-950/60 dark:text-indigo-400">
              <Sliders className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-slate-800 dark:text-slate-100">
                {t('title', '模型 Context 与价格自定义管理')}
              </h2>
              <div className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
                <ShieldCheck className="h-3.5 w-3.5 text-emerald-500" />
                <span>{t('hermesParity', '对标 Hermes v0.21.0 model_overrides · 实时热生效')}</span>
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            data-testid="close-overrides-dialog"
            className="rounded-lg p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-200"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {/* Preloaded SKUs Quick Clone */}
          <div>
            <label className="mb-2 block text-xs font-semibold text-slate-700 dark:text-slate-300">
              {t('cloneTemplate', '2026 主流新模型 SKU 预置模板（点击一键克隆）:')}
            </label>
            <div className="flex flex-wrap gap-2">
              {preloadedSkus.map((sku) => (
                <button
                  key={sku.model_id}
                  type="button"
                  onClick={() => {
                    applySkuToForm(sku);
                  }}
                  data-testid={`clone-sku-${sku.model_id}`}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:border-indigo-400 hover:bg-indigo-50/50 dark:border-slate-800 dark:bg-slate-800 dark:text-slate-200"
                >
                  <Sparkles className="h-3.5 w-3.5 text-indigo-500" />
                  <span>{sku.display_name}</span>
                  <span className="text-slate-400">({Math.round(sku.default_context_window / 1000)}k)</span>
                </button>
              ))}
            </div>
          </div>

          {/* Form Configuration Grid */}
          <div className="grid grid-cols-2 gap-4 rounded-xl border border-slate-100 bg-slate-50/60 p-4 dark:border-slate-800 dark:bg-slate-800/40">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-700 dark:text-slate-300">
                {t('modelIdLabel', '目标模型 ID / 别名')}
              </label>
              <input
                type="text"
                value={selectedModelId}
                onChange={(e) => {
                  setSelectedModelId(e.target.value);
                }}
                data-testid="input-model-id"
                placeholder="e.g. glm-5.3-flash, qwen-3.8-max"
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 transition focus:border-indigo-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-slate-700 dark:text-slate-300">
                {t('currencyLabel', '计费币种')}
              </label>
              <select
                value={currency}
                onChange={(e) => {
                  setCurrency(e.target.value as CurrencyType);
                }}
                data-testid="select-currency"
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 transition focus:border-indigo-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              >
                <option value="USD">USD ($)</option>
                <option value="CNY">CNY (¥)</option>
              </select>
            </div>

            <div>
              <div className="flex justify-between text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                <span>{t('contextWindowLabel', 'Context Window (tokens)')}</span>
                <span className="font-mono text-indigo-600 dark:text-indigo-400">
                  {contextWindow.toLocaleString()} tokens
                </span>
              </div>
              <input
                type="range"
                min={4096}
                max={2000000}
                step={4096}
                value={contextWindow}
                onChange={(e) => {
                  setContextWindow(Number(e.target.value));
                }}
                data-testid="slider-context-window"
                className="w-full accent-indigo-600"
              />
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-slate-700 dark:text-slate-300">
                {t('maxOutputLabel', 'Max Output Tokens (输出上限)')}
              </label>
              <input
                type="number"
                value={maxOutput}
                onChange={(e) => {
                  setMaxOutput(Number(e.target.value));
                }}
                data-testid="input-max-output"
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 transition focus:border-indigo-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-slate-700 dark:text-slate-300">
                {t('inputPriceLabel', '输入单价 (每 1M tokens)')}
              </label>
              <input
                type="number"
                step={0.01}
                value={inputPrice}
                onChange={(e) => {
                  setInputPrice(Number(e.target.value));
                }}
                data-testid="input-price-input"
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 transition focus:border-indigo-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-slate-700 dark:text-slate-300">
                {t('outputPriceLabel', '输出单价 (每 1M tokens)')}
              </label>
              <input
                type="number"
                step={0.01}
                value={outputPrice}
                onChange={(e) => {
                  setOutputPrice(Number(e.target.value));
                }}
                data-testid="output-price-input"
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 transition focus:border-indigo-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>
          </div>

          {/* BYOK Live Cost Calculator Subcomponent */}
          <ByokCostCalculatorCard modelId={selectedModelId} />

          {/* Active Overrides Table */}
          {overrides.length > 0 && (
            <div>
              <h4 className="mb-2 text-xs font-semibold text-slate-700 dark:text-slate-300">
                {t('activeOverrides', '已保存的模型覆写列表:')}
              </h4>
              <div className="space-y-1.5">
                {overrides.map((item) => (
                  <div
                    key={item.model_id}
                    className="flex items-center justify-between rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs dark:border-slate-800 dark:bg-slate-800"
                  >
                    <div className="flex items-center gap-2">
                      <Zap className="h-3.5 w-3.5 text-indigo-500" />
                      <strong className="text-slate-800 dark:text-slate-100">{item.model_id}</strong>
                      <span className="text-slate-500">
                        ({item.custom_context_window ? `${Math.round(item.custom_context_window / 1000)}k tokens` : 'Default'} · {item.currency})
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          applyModelToForm(item);
                        }}
                        className="text-indigo-600 hover:underline dark:text-indigo-400"
                      >
                        {t('loadToForm', '加载编辑')}
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          void handleDelete(item.model_id);
                        }}
                        data-testid={`delete-override-${item.model_id}`}
                        className="text-rose-500 hover:text-rose-700"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-slate-100 bg-slate-50/50 px-6 py-4 dark:border-slate-800 dark:bg-slate-900/50">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            {t('close', '关闭')}
          </button>
          <button
            type="button"
            onClick={() => {
              void handleSave();
            }}
            disabled={isSaving}
            data-testid="save-override-btn"
            className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-5 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:opacity-50"
          >
            <Check className="h-4 w-4" />
            <span>{t('saveAndApply', '保存并实时生效')}</span>
          </button>
        </div>
      </div>
    </dialog>
  );
};
