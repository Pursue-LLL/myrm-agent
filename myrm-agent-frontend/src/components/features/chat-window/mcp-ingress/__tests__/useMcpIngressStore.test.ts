import { describe, it, expect, beforeEach } from 'vitest';
import {
  useMcpIngressStore,
  extractMcpCandidateUrl,
} from '../useMcpIngressStore';

describe('useMcpIngressStore & extractMcpCandidateUrl', () => {
  beforeEach(() => {
    useMcpIngressStore.getState().reset();
  });

  it('correctly sniffs MCP and Skill URLs from free-form chat text', () => {
    expect(extractMcpCandidateUrl('请调用这个服务 http://localhost:8000/sse 查数据')).toBe('http://localhost:8000/sse');
    expect(extractMcpCandidateUrl('参考 https://github.com/modelcontextprotocol/servers 中的工具')).toBe('https://github.com/modelcontextprotocol/servers');
    expect(extractMcpCandidateUrl('今天天气真好 https://www.google.com')).toBeNull();
    expect(extractMcpCandidateUrl('纯文本没有任何链接')).toBeNull();
  });

  it('updates detectedUrl state when sniffInputText matches', () => {
    const candidate = useMcpIngressStore.getState().sniffInputText('接入 https://api.weather-mcp.io/sse 谢谢');
    expect(candidate).toBe('https://api.weather-mcp.io/sse');
    expect(useMcpIngressStore.getState().detectedUrl).toBe('https://api.weather-mcp.io/sse');

    useMcpIngressStore.getState().dismissDetectedUrl();
    expect(useMcpIngressStore.getState().detectedUrl).toBeNull();
  });

  it('probes URL and discovers remote MCP tools with latency metric', async () => {
    const probe = await useMcpIngressStore.getState().probeUrl('https://api.financial-tools.org/mcp/sse');
    expect(probe.serviceName).toContain('FINANCIAL-TOOLS');
    expect(probe.protocol).toBe('mcp-sse');
    expect(probe.securityLevel).toBe('safe');
    expect(probe.tools.length).toBeGreaterThan(0);
    expect(probe.probeDurationMs).toBeGreaterThanOrEqual(0);

    const stored = useMcpIngressStore.getState().probes['https://api.financial-tools.org/mcp/sse'];
    expect(stored).toEqual(probe);
  });

  it('mounts service to session and marks mounted status', async () => {
    const probe = await useMcpIngressStore.getState().probeUrl('https://mcp.github.com/skills/git');
    const success = await useMcpIngressStore.getState().mountService({
      url: 'https://mcp.github.com/skills/git',
      probe,
      mountMode: 'session_ephemeral',
      sessionId: 'chat-sess-42',
    });

    expect(success).toBe(true);
    expect(useMcpIngressStore.getState().mountStatuses['https://mcp.github.com/skills/git']).toBe('mounted');
    expect(useMcpIngressStore.getState().mountedSessions['chat-sess-42']).toContain('https://mcp.github.com/skills/git');
  });
});
