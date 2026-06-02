/**
 * 代理 API：调用提供商的 /models 接口
 * 用于绕过 CORS 限制，直接从提供商获取模型列表
 */

import { NextRequest, NextResponse } from 'next/server';

interface ModelObject {
  id: string;
  object?: string;
  created?: number;
  owned_by?: string;
}

interface ModelsResponse {
  object?: string;
  data?: ModelObject[];
  // 某些提供商可能直接返回数组
  models?: ModelObject[];
}

/**
 * 从 apiUrl 提取 hostname 和路径前缀，构造多个候选 /models URL
 * 尝试所有候选 URL，返回第一个成功的
 *
 * 支持多种 URL 格式：
 *   - https://api.svips.org/v1/chat/completions → /v1/models
 *   - https://api.svips.org → /v1/models, /models
 *   - https://api.deepseek.com → /models, /v1/models
 */
async function fetchModelsFromCandidates(
  apiUrl: string,
  apiKey: string,
): Promise<{ modelsUrl: string; response: Response }> {
  const base = apiUrl.replace(/\/+$/, '');

  // 构造候选 URL 列表
  const candidates: string[] = [];

  // 如果恰好是 /models 直接尝试
  if (base.endsWith('/models')) {
    candidates.push(base);
  }

  // 提取到 /{version} 层级（去掉最后1-2段路径）
  // e.g. /v1/chat/completions → /v1
  // 注意避开 https:// 的斜杠
  const schemeIdx = base.indexOf('://');
  const startIdx = schemeIdx !== -1 ? schemeIdx + 3 : 0;

  const lastSlash = base.lastIndexOf('/');
  if (lastSlash > startIdx) {
    const parent1 = base.slice(0, lastSlash);
    candidates.push(`${parent1}/models`);
    const secondSlash = parent1.lastIndexOf('/');
    if (secondSlash > startIdx) {
      candidates.push(`${parent1.slice(0, secondSlash)}/models`);
    }
  }

  // 对于不带版本号的裸域名，尝试常见路径模式
  // e.g. https://api.svips.org → /v1/models
  // 检测是否是裸域名（只有 hostname，没有路径）
  const pathStart = base.indexOf('/', 8); // 跳过 https://
  if (pathStart === -1 || base.slice(pathStart).length <= 1) {
    // 裸域名，尝试常见的 models 端点路径
    candidates.push(`${base}/v1/models`);
    candidates.push(`${base}/api/v1/models`);
    candidates.push(`${base}/api/models`);
  }

  // 通用兜底
  candidates.push(`${base}/models`);

  // 去重
  const unique = [...new Set(candidates)];

  const headers = {
    Authorization: `Bearer ${apiKey}`,
    Accept: 'application/json',
    'Content-Type': 'application/json',
  };

  let bestResponse: { modelsUrl: string; response: Response } | null = null;
  let lastError: unknown = null;

  for (const modelsUrl of unique) {
    try {
      const response = await fetch(modelsUrl, {
        method: 'GET',
        headers,
        signal: AbortSignal.timeout(8_000),
      });
      if (response.ok) {
        return { modelsUrl, response };
      }
      bestResponse = { modelsUrl, response };
    } catch (e) {
      lastError = e;
      // 记录网络错误，继续尝试下一个候选 URL
    }
  }

  // 全部失败，如果有返回 HTTP 错误的响应，直接返回用于提取错误信息
  if (bestResponse) {
    return bestResponse;
  }

  // 如果所有的请求都因为网络/超时抛出异常，向外抛出最后一个异常
  if (lastError) {
    throw lastError;
  }

  throw new Error('No candidate URLs generated');
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { apiUrl, apiKey } = body as { apiUrl: string; apiKey: string };

    if (!apiUrl) {
      return NextResponse.json({ success: false, error: 'API URL is required' }, { status: 400 });
    }

    if (!apiKey) {
      return NextResponse.json({ success: false, error: 'API Key is required' }, { status: 400 });
    }

    const { modelsUrl, response } = await fetchModelsFromCandidates(apiUrl, apiKey);

    if (!response.ok) {
      const errorText = await response.text();
      console.error(`Failed to fetch models from ${modelsUrl}: ${response.status} - ${errorText}`);
      return NextResponse.json(
        {
          success: false,
          error: `Provider returned ${response.status}: ${errorText.slice(0, 200)}`,
        },
        { status: response.status },
      );
    }

    const text = await response.text();
    let data: ModelsResponse;
    try {
      data = JSON.parse(text) as ModelsResponse;
    } catch (e) {
      console.error(`Failed to parse response from ${modelsUrl} as JSON:`, e);
      return NextResponse.json(
        {
          success: false,
          error: `Provider returned invalid JSON format. Body prefix: ${text.slice(0, 100)}`,
        },
        { status: 502 },
      );
    }

    // 处理不同提供商的响应格式
    // OpenAI 格式：{ object: 'list', data: [...] }
    // 某些提供商可能：{ models: [...] }
    // 某些提供商可能直接返回数组
    let models: string[] = [];

    if (Array.isArray(data.data)) {
      models = data.data.map((m) => m.id).filter(Boolean);
    } else if (Array.isArray(data.models)) {
      models = data.models.map((m) => m.id).filter(Boolean);
    } else if (Array.isArray(data)) {
      models = (data as ModelObject[]).map((m) => m.id).filter(Boolean);
    }

    return NextResponse.json({
      success: true,
      models,
      raw: data,
    });
  } catch (error) {
    const isTimeout = error instanceof DOMException && error.name === 'TimeoutError';
    const message = isTimeout
      ? 'Request timed out — check if the API endpoint is reachable'
      : error instanceof Error
        ? error.message
        : 'Unknown error';

    if (!isTimeout) console.error('Error in proxy-models:', error);

    return NextResponse.json({ success: false, error: message }, { status: isTimeout ? 504 : 500 });
  }
}
