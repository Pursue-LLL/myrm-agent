import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { McpLinkMountCard } from '../McpLinkMountCard';
import { useMcpIngressStore } from '../useMcpIngressStore';
import type { McpProbeResult } from '../mcpIngressTypes';

describe('McpLinkMountCard', () => {
  beforeEach(() => {
    useMcpIngressStore.getState().reset();
    vi.restoreAllMocks();
  });

  const mockProbe: McpProbeResult = {
    url: 'https://api.github-tools.com/sse',
    serviceName: 'GITHUB-TOOLS Remote MCP',
    protocol: 'mcp-sse',
    securityLevel: 'safe',
    tools: [
      { name: 'create_issue', description: 'Create a GitHub issue' },
      { name: 'list_commits', description: 'List commits for repo' },
    ],
    probeDurationMs: 64,
    probedAt: Date.now(),
  };

  it('renders service name, protocol badge, and discovered tools', () => {
    render(<McpLinkMountCard probe={mockProbe} sessionId="sess-test-1" />);
    expect(screen.getByText('GITHUB-TOOLS Remote MCP')).toBeDefined();
    expect(screen.getByText('MCP (SSE)')).toBeDefined();
    expect(screen.getByText('安全沙箱合格')).toBeDefined();
    expect(screen.getByText('create_issue')).toBeDefined();
    expect(screen.getByText('list_commits')).toBeDefined();
    expect(screen.getByText('64ms 握手探针')).toBeDefined();
  });

  it('handles ephemeral session mount on button click', async () => {
    const onMounted = vi.fn();
    render(<McpLinkMountCard probe={mockProbe} sessionId="sess-test-1" onMounted={onMounted} />);

    const mountBtn = screen.getByRole('button', { name: /一键挂载至本会话/ });
    fireEvent.click(mountBtn);

    await waitFor(() => {
      expect(screen.getByText('已成功热挂载')).toBeDefined();
      expect(onMounted).toHaveBeenCalledWith('session_ephemeral');
    });
  });

  it('handles persistent agent mount on button click', async () => {
    const onMounted = vi.fn();
    render(<McpLinkMountCard probe={mockProbe} sessionId="sess-test-1" onMounted={onMounted} />);

    const bindBtn = screen.getByRole('button', { name: /持久绑定至当前智能体/ });
    fireEvent.click(bindBtn);

    await waitFor(() => {
      expect(screen.getByText('已成功热挂载')).toBeDefined();
      expect(onMounted).toHaveBeenCalledWith('agent_persistent');
    });
  });
});
