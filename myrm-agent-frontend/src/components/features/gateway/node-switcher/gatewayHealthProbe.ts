/**
 * Gateway Health Probe & Node URL Normalization Engine
 * 网关节点健康探测器、RTT 延迟计算与地址规范化引擎
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 所有 if 显式包裹大括号；
 * 3. 行数严格受控在 400 行以内。
 */

import {
  GatewayNodeDescriptor,
  GatewayNodeStatus,
  ProbeResult,
} from './gatewayNodeTypes';

export function normalizeEndpointUrl(rawUrl: string): string {
  let url = rawUrl.trim();
  if (!url.startsWith('http://') && !url.startsWith('https://')) {
    url = `http://${url}`;
  }
  return url.replace(/\/+$/, '');
}

export type CustomFetcher = (
  url: string,
  options?: RequestInit
) => Promise<{ status: number; ok: boolean; json?: () => Promise<unknown> }>;

export async function probeGatewayNode(
  node: GatewayNodeDescriptor,
  customFetcher?: CustomFetcher
): Promise<ProbeResult> {
  const startTime = Date.now();
  const normalizedUrl = normalizeEndpointUrl(node.endpointUrl);
  const healthUrl = `${normalizedUrl}/health`;

  try {
    let statusCode = 200;
    let isOk = true;

    if (customFetcher) {
      const response = await customFetcher(healthUrl);
      statusCode = response.status;
      isOk = response.ok;
    } else if (typeof fetch !== 'undefined') {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => {
        controller.abort();
      }, 3500);

      const response = await fetch(healthUrl, {
        method: 'GET',
        headers: node.token ? { Authorization: `Bearer ${node.token}` } : {},
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      statusCode = response.status;
      isOk = response.ok;
    }

    const pingMs = Date.now() - startTime;

    if (isOk && statusCode < 300) {
      const status: GatewayNodeStatus = pingMs > 1500 ? 'degraded' : 'healthy';
      return {
        nodeId: node.id,
        status,
        pingMs,
        hardwareInfo: node.hardwareInfo,
      };
    }

    return {
      nodeId: node.id,
      status: 'degraded',
      pingMs,
      error: `响应异常 HTTP 状态码: ${statusCode}`,
    };
  } catch (err: unknown) {
    const pingMs = Date.now() - startTime;
    const message = err instanceof Error ? err.message : String(err);
    return {
      nodeId: node.id,
      status: 'unreachable',
      pingMs,
      error: `连接失败: ${message}`,
    };
  }
}

export function filterAndSortNodes(
  nodes: GatewayNodeDescriptor[],
  query?: string,
  tagFilter?: string
): GatewayNodeDescriptor[] {
  let result = [...nodes];

  if (tagFilter && tagFilter !== 'all') {
    result = result.filter((n) => n.tags.includes(tagFilter));
  }

  if (query && query.trim().length > 0) {
    const q = query.toLowerCase().trim();
    result = result.filter(
      (n) =>
        n.name.toLowerCase().includes(q) ||
        n.endpointUrl.toLowerCase().includes(q) ||
        n.tags.some((t) => t.toLowerCase().includes(q))
    );
  }

  // 排序：默认节点排在第一位，其次 healthy，其次 ping 升序
  result.sort((a, b) => {
    if (a.isDefault) {
      return -1;
    }
    if (b.isDefault) {
      return 1;
    }

    const statusScore: Record<GatewayNodeStatus, number> = {
      healthy: 1,
      degraded: 2,
      checking: 3,
      unreachable: 4,
      offline: 5,
    };

    const diffStatus = statusScore[a.status] - statusScore[b.status];
    if (diffStatus !== 0) {
      return diffStatus;
    }

    return a.pingMs - b.pingMs;
  });

  return result;
}
