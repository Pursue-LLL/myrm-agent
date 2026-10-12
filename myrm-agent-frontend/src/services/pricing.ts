/**
 * [INPUT]
 * - @/lib/api::apiRequest (POS: HTTP client wrapper)
 *
 * [OUTPUT]
 * - ModelPricingItem: 模型四维单价矩阵条目接口
 * - ModelPricingResponse: 模型单价查询响应接口
 * - fetchModelPricing: 获取四维模型单价与 Prompt Cache 折扣
 *
 * [POS]
 * 前端模型经济学与定价服务层。向后端查询以 $/1M tokens 计价的模型单价与 Cache 节省率。
 */

import { apiRequest } from '@/lib/api';

export interface ModelPricingItem {
  model: string;
  input_cost_per_mtoken: number;
  output_cost_per_mtoken: number;
  cache_read_cost_per_mtoken: number | null;
  cache_write_cost_per_mtoken: number | null;
  cache_read_discount: number | null;
  supports_prompt_caching: boolean;
}

export interface ModelPricingResponse {
  models: Record<string, ModelPricingItem>;
}

interface CacheEntry {
  data: ModelPricingResponse;
  timestamp: number;
}

const CACHE_TTL_MS = 60_000;
const pricingMemoryCache = new Map<string, CacheEntry>();

/**
 * 获取指定或主流标杆模型的四维单价矩阵与 Cache 折扣数据。
 * @param model 可选指定模型名称
 */
export async function fetchModelPricing(model?: string): Promise<ModelPricingResponse> {
  const cacheKey = model ? model.trim().toLowerCase() : '__default__';
  const cached = pricingMemoryCache.get(cacheKey);

  if (cached && Date.now() - cached.timestamp < CACHE_TTL_MS) {
    return cached.data;
  }

  const endpoint = model
    ? `/config/model-pricing?model=${encodeURIComponent(model.trim())}`
    : '/config/model-pricing';

  try {
    const data = await apiRequest<ModelPricingResponse>(endpoint, { silent: true });
    pricingMemoryCache.set(cacheKey, {
      data,
      timestamp: Date.now(),
    });
    return data;
  } catch {
    // 降级兜底：网络异常或服务未就绪时返回空字典，避免阻塞界面渲染
    return { models: {} };
  }
}
