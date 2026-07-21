import { describe, expect, it } from 'vitest';

import type { MCPServiceConfig } from '@/store/config/types';
import {
  canonicalizeMCPTransport,
  normalizeMCPKeepaliveInterval,
  normalizeMCPServiceConfig,
  normalizeMCPServiceConfigs,
} from '@/lib/utils/mcpConfigNormalizer';

describe('mcpConfigNormalizer', () => {
  it('canonicalizeMCPTransport 应该归一化 transport 别名', () => {
    expect(canonicalizeMCPTransport('http')).toBe('streamable_http');
    expect(canonicalizeMCPTransport('streamable-http')).toBe('streamable_http');
    expect(canonicalizeMCPTransport('streamableHttp')).toBe('streamable_http');
    expect(canonicalizeMCPTransport('sse')).toBe('sse');
    expect(canonicalizeMCPTransport('stdio')).toBe('stdio');
  });

  it('normalizeMCPKeepaliveInterval 应该只允许 remote transport 使用 keepalive', () => {
    expect(normalizeMCPKeepaliveInterval('stdio', 30)).toBeNull();
    expect(normalizeMCPKeepaliveInterval('sse', 4)).toBeNull();
    expect(normalizeMCPKeepaliveInterval('streamable_http', 12)).toBe(12);
  });

  it('normalizeMCPServiceConfig 应该清洗 stdio keepalive 并收敛 type', () => {
    const raw = {
      name: 'legacy-http',
      type: 'http',
      url: 'https://example.com/mcp',
      description: 'legacy',
      enabled: true,
      keepaliveInterval: 20,
    } as unknown as MCPServiceConfig;

    const normalized = normalizeMCPServiceConfig(raw);
    expect(normalized.type).toBe('streamable_http');
    expect(normalized.keepaliveInterval).toBe(20);

    const stdio = normalizeMCPServiceConfig({
      ...normalized,
      type: 'stdio',
      command: 'python',
      keepaliveInterval: 20,
    });
    expect(stdio.keepaliveInterval).toBeNull();
  });

  it('normalizeMCPServiceConfigs 应该批量归一化', () => {
    const list = normalizeMCPServiceConfigs([
      {
        name: 'a',
        type: 'stdio',
        command: 'python',
        description: 'a',
        enabled: true,
        keepaliveInterval: 10,
      },
      {
        name: 'b',
        type: 'sse',
        url: 'https://example.com/sse',
        description: 'b',
        enabled: true,
        keepaliveInterval: 10,
      },
    ]);
    expect(list[0].keepaliveInterval).toBeNull();
    expect(list[1].keepaliveInterval).toBe(10);
  });
});
