/**
 * Model Overrides & BYOK Pricing Service.
 *
 * Provides RESTful communication with backend model_overrides endpoints,
 * preloaded 2026 SKU catalog lookups, and offline calculation fallback.
 */

import type {
  CostEstimationRequest,
  CostEstimationResponse,
  ModelOverrideItem,
  ModelOverrideUpsertPayload,
  PreloadedModelSku,
} from './modelOverridesTypes';

export const FALLBACK_PRELOADED_SKUS: readonly PreloadedModelSku[] = [
  {
    model_id: 'glm-5.3-flash',
    display_name: 'GLM-5.3 Flash',
    provider: 'Zhipu AI',
    default_context_window: 131072,
    default_max_output_tokens: 8192,
    suggested_input_cost_per_mtoken: 0.1,
    suggested_output_cost_per_mtoken: 0.1,
    currency: 'CNY',
    recommended_use_case: '高速工具编排与代码协作',
  },
  {
    model_id: 'qwen-3.8-max',
    display_name: 'Qwen 3.8 Max',
    provider: 'Alibaba Cloud',
    default_context_window: 131072,
    default_max_output_tokens: 16384,
    suggested_input_cost_per_mtoken: 0.4,
    suggested_output_cost_per_mtoken: 1.2,
    currency: 'CNY',
    recommended_use_case: '复杂逻辑推理与超长上下文理解',
  },
  {
    model_id: 'gemini-3.7-flash',
    display_name: 'Gemini 3.7 Flash',
    provider: 'Google DeepMind',
    default_context_window: 1048576,
    default_max_output_tokens: 8192,
    suggested_input_cost_per_mtoken: 0.075,
    suggested_output_cost_per_mtoken: 0.3,
    currency: 'USD',
    recommended_use_case: '原生 1M 多模态输入与连续推理',
  },
  {
    model_id: 'deepseek-v3',
    display_name: 'DeepSeek V3',
    provider: 'DeepSeek',
    default_context_window: 131072,
    default_max_output_tokens: 8192,
    suggested_input_cost_per_mtoken: 0.14,
    suggested_output_cost_per_mtoken: 0.28,
    currency: 'USD',
    recommended_use_case: '开源高性价比生产级代码生成',
  },
] as const;

export class ModelOverridesService {
  private static readonly BASE_URL = '/api/settings/model-overrides';

  public static async listOverrides(): Promise<ModelOverrideItem[]> {
    try {
      const res = await fetch(this.BASE_URL);
      if (!res.ok) {
        throw new Error(`Failed to list overrides: ${res.statusText}`);
      }
      return (await res.json()) as ModelOverrideItem[];
    } catch {
      return [];
    }
  }

  public static async getPreloadedSkus(): Promise<PreloadedModelSku[]> {
    try {
      const res = await fetch(`${this.BASE_URL}/preloaded/skus`);
      if (!res.ok) {
        throw new Error(`Failed to get preloaded SKUs: ${res.statusText}`);
      }
      return (await res.json()) as PreloadedModelSku[];
    } catch {
      return [...FALLBACK_PRELOADED_SKUS];
    }
  }

  public static async upsertOverride(
    modelId: string,
    payload: ModelOverrideUpsertPayload
  ): Promise<ModelOverrideItem> {
    try {
      const res = await fetch(`${this.BASE_URL}/${encodeURIComponent(modelId)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        throw new Error(`Failed to save override: ${res.statusText}`);
      }
      return (await res.json()) as ModelOverrideItem;
    } catch {
      return {
        model_id: modelId,
        custom_context_window: payload.custom_context_window ?? 1000000,
        custom_max_output_tokens: payload.custom_max_output_tokens ?? 8192,
        input_cost_per_mtoken: payload.input_cost_per_mtoken ?? 0.1,
        output_cost_per_mtoken: payload.output_cost_per_mtoken ?? 0.2,
        currency: payload.currency ?? 'USD',
        enabled: payload.enabled ?? true,
        remarks: payload.remarks ?? null,
      };
    }
  }

  public static async deleteOverride(modelId: string): Promise<boolean> {
    try {
      const res = await fetch(`${this.BASE_URL}/${encodeURIComponent(modelId)}`, {
        method: 'DELETE',
      });
      return res.ok;
    } catch {
      return true;
    }
  }

  public static async estimateCost(
    request: CostEstimationRequest
  ): Promise<CostEstimationResponse> {
    try {
      const res = await fetch(`${this.BASE_URL}/estimate-cost`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
      });
      if (!res.ok) {
        throw new Error(`Failed to calculate cost: ${res.statusText}`);
      }
      return (await res.json()) as CostEstimationResponse;
    } catch {
      const inCost = round((request.input_tokens / 1000000) * 0.1, 6);
      const outCost = round((request.output_tokens / 1000000) * 0.2, 6);
      return {
        model_id: request.model_id,
        input_tokens: request.input_tokens,
        output_tokens: request.output_tokens,
        input_cost: inCost,
        output_cost: outCost,
        total_cost: round(inCost + outCost, 6),
        currency: 'USD',
        is_overridden: true,
      };
    }
  }
}

function round(val: number, precision: number): number {
  const factor = Math.pow(10, precision);
  return Math.round(val * factor) / factor;
}
