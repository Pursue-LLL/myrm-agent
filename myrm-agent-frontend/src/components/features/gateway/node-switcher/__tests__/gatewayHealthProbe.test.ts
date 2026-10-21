import { describe, it, expect, vi } from 'vitest';
import {
  normalizeEndpointUrl,
  probeGatewayNode,
  filterAndSortNodes,
  CustomFetcher,
} from '../gatewayHealthProbe';
import { GatewayNodeDescriptor } from '../gatewayNodeTypes';

describe('gatewayHealthProbe', () => {
  describe('normalizeEndpointUrl', () => {
    it('为缺少 http/https 前缀的地址自动补齐 http://', () => {
      expect(normalizeEndpointUrl('192.168.1.100:8000')).toBe('http://192.168.1.100:8000');
      expect(normalizeEndpointUrl('localhost:3000/')).toBe('http://localhost:3000');
    });

    it('剔除尾部多余的斜杠并保留 https 协议', () => {
      expect(normalizeEndpointUrl('https://my-gateway.internal///')).toBe('https://my-gateway.internal');
      expect(normalizeEndpointUrl('   http://10.0.0.1:8080/   ')).toBe('http://10.0.0.1:8080');
    });
  });

  describe('probeGatewayNode', () => {
    const mockNode: GatewayNodeDescriptor = {
      id: 'node-1',
      name: 'Test Node',
      endpointUrl: 'http://localhost:8000',
      isDefault: true,
      pingMs: 0,
      status: 'offline',
      tags: ['local'],
      lastCheckedAt: '',
    };

    it('使用 customFetcher 模拟成功响应并返回 healthy 状态', async () => {
      const mockFetcher: CustomFetcher = vi.fn().mockResolvedValue({
        status: 200,
        ok: true,
      });

      const result = await probeGatewayNode(mockNode, mockFetcher);
      expect(result.nodeId).toBe('node-1');
      expect(result.status).toBe('healthy');
      expect(result.pingMs).toBeGreaterThanOrEqual(0);
      expect(mockFetcher).toHaveBeenCalledWith('http://localhost:8000/health');
    });

    it('当返回非 200 响应时返回 degraded 状态', async () => {
      const mockFetcher: CustomFetcher = vi.fn().mockResolvedValue({
        status: 500,
        ok: false,
      });

      const result = await probeGatewayNode(mockNode, mockFetcher);
      expect(result.nodeId).toBe('node-1');
      expect(result.status).toBe('degraded');
      expect(result.error).toContain('500');
    });

    it('当网络请求异常或超时抛出错误时返回 unreachable 状态', async () => {
      const mockFetcher: CustomFetcher = vi.fn().mockRejectedValue(new Error('Connection refused'));

      const result = await probeGatewayNode(mockNode, mockFetcher);
      expect(result.nodeId).toBe('node-1');
      expect(result.status).toBe('unreachable');
      expect(result.error).toContain('Connection refused');
    });
  });

  describe('filterAndSortNodes', () => {
    const sampleNodes: GatewayNodeDescriptor[] = [
      {
        id: 'node-a',
        name: 'Cloud Node',
        endpointUrl: 'https://cloud.internal',
        isDefault: false,
        pingMs: 120,
        status: 'healthy',
        tags: ['cloud'],
        lastCheckedAt: '',
      },
      {
        id: 'node-b',
        name: 'Local RTX 4090',
        endpointUrl: 'http://192.168.1.50:8000',
        isDefault: true,
        pingMs: 15,
        status: 'healthy',
        tags: ['lan', 'gpu'],
        lastCheckedAt: '',
      },
      {
        id: 'node-c',
        name: 'Mac Mini M2',
        endpointUrl: 'http://192.168.1.51:8000',
        isDefault: false,
        pingMs: 300,
        status: 'degraded',
        tags: ['lan'],
        lastCheckedAt: '',
      },
    ];

    it('默认优先排在第一位，其余按状态和 ping 升序排列', () => {
      const sorted = filterAndSortNodes(sampleNodes);
      expect(sorted[0].id).toBe('node-b'); // isDefault
      expect(sorted[1].id).toBe('node-a'); // healthy, ping 120
      expect(sorted[2].id).toBe('node-c'); // degraded, ping 300
    });

    it('支持按 tag 进行精确过滤', () => {
      const filtered = filterAndSortNodes(sampleNodes, undefined, 'gpu');
      expect(filtered.length).toBe(1);
      expect(filtered[0].id).toBe('node-b');
    });

    it('支持按关键词模糊搜索名称、URL 或标签', () => {
      const byName = filterAndSortNodes(sampleNodes, 'Cloud');
      expect(byName.length).toBe(1);
      expect(byName[0].id).toBe('node-a');

      const byIp = filterAndSortNodes(sampleNodes, '192.168.1.51');
      expect(byIp.length).toBe(1);
      expect(byIp[0].id).toBe('node-c');
    });
  });
});
