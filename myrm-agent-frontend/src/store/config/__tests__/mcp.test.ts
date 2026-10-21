import { describe, expect, it } from 'vitest';

import type { MCPServiceConfig } from '@/store/config/types';
import { addMCPConfig, setMCPConfigs, updateMCPConfig } from '@/store/config/mcp';

describe('store/config/mcp', () => {
  it('setMCPConfigs 应归一化 transport 与 keepalive', () => {
    const input = [
      {
        name: 'legacy-http',
        type: 'http',
        url: 'https://example.com/mcp',
        description: '',
        enabled: true,
        keepaliveInterval: 15,
      },
      {
        name: 'legacy-stdio',
        type: 'stdio',
        command: 'python',
        description: '',
        enabled: true,
        keepaliveInterval: 15,
      },
    ] as unknown as MCPServiceConfig[];

    const normalized = setMCPConfigs(input);
    expect(normalized[0].type).toBe('streamable_http');
    expect(normalized[0].keepaliveInterval).toBe(15);
    expect(normalized[1].keepaliveInterval).toBeNull();
  });

  it('add/update 应保持归一化', () => {
    const initial = setMCPConfigs([
      {
        name: 'a',
        type: 'sse',
        url: 'https://example.com/sse',
        description: '',
        enabled: true,
        keepaliveInterval: 10,
      },
    ]);

    const added = addMCPConfig(initial, {
      name: 'b',
      type: 'http',
      url: 'https://example.com/mcp',
      description: '',
      enabled: true,
      keepaliveInterval: 20,
    } as unknown as MCPServiceConfig);
    expect(added[1].type).toBe('streamable_http');

    const updated = updateMCPConfig(added, 1, {
      ...added[1],
      type: 'stdio',
      command: 'python',
      keepaliveInterval: 20,
    });
    expect(updated[1].keepaliveInterval).toBeNull();
  });
});
