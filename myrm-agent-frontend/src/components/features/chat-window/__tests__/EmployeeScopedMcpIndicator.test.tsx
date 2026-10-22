'use client';

/**
 * [INPUT]: EmployeeScopedMcpIndicator.tsx 与 mock 员工作用域数据
 * [OUTPUT]: 验证员工作用域指示胶囊条渲染、严格模式徽章、裁剪越权统计与详情折叠展开
 * [POS]: myrm-agent-frontend/src/components/features/chat-window/__tests__/EmployeeScopedMcpIndicator.test.tsx
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
  EmployeeScopedMcpIndicator,
  McpScopingToolItem,
} from '../EmployeeScopedMcpIndicator';

const mockBlockedList: McpScopingToolItem[] = [
  {
    serverName: 'postgres',
    toolName: 'drop_database',
    isAllowed: false,
    reason: 'Tool not in allowlist for server postgres',
  },
  {
    serverName: 'aws',
    toolName: 'terminate_instance',
    isAllowed: false,
    reason: 'Server aws is not allowed for this agent',
  },
];

const mockAllowedList: McpScopingToolItem[] = [
  {
    serverName: 'github',
    toolName: 'create_issue',
    isAllowed: true,
    reason: 'Allowed by employee scope policy',
  },
  {
    serverName: 'github',
    toolName: 'read_repo',
    isAllowed: true,
    reason: 'Allowed by employee scope policy',
  },
];

describe('EmployeeScopedMcpIndicator', () => {
  it('renders capsule header with agent ID, strict mode, servers and tools counts', () => {
    render(
      <EmployeeScopedMcpIndicator
        agentId="developer-bot"
        allowedServers={['github', 'postgres']}
        allowedToolsCount={5}
        strictMode={true}
      />
    );

    expect(screen.getByTestId('employee-scoped-mcp-indicator')).toBeInTheDocument();
    expect(screen.getByText('MCP 员工作用域')).toBeInTheDocument();
    expect(screen.getByTestId('agent-id-badge')).toHaveTextContent('@developer-bot');
    expect(screen.getByTestId('strict-mode-badge')).toHaveTextContent('严格物理隔离');
    expect(screen.getByText('2 个服务')).toBeInTheDocument();
    expect(screen.getByText('5 个工具可用')).toBeInTheDocument();
  });

  it('renders blocked tools badge when blockedToolsCount > 0', () => {
    render(
      <EmployeeScopedMcpIndicator
        agentId="junior-analyst"
        allowedServers={['sqlite']}
        allowedToolsCount={2}
        blockedToolsCount={3}
      />
    );

    const blockedBadge = screen.getByTestId('blocked-tools-badge');
    expect(blockedBadge).toBeInTheDocument();
    expect(blockedBadge).toHaveTextContent('已裁剪 3 个越权工具');
  });

  it('toggles scope details on expand button click and displays lists', () => {
    render(
      <EmployeeScopedMcpIndicator
        agentId="developer-bot"
        allowedServers={['github']}
        allowedToolsCount={2}
        blockedToolsCount={2}
        blockedToolsList={mockBlockedList}
        allowedToolsList={mockAllowedList}
      />
    );

    // Initially collapsed
    expect(screen.queryByTestId('scope-details-section')).not.toBeInTheDocument();

    // Click toggle button
    const toggleBtn = screen.getByTestId('toggle-scope-details-btn');
    fireEvent.click(toggleBtn);

    // Expanded details
    expect(screen.getByTestId('scope-details-section')).toBeInTheDocument();
    expect(screen.getByTestId('allowed-server-github')).toHaveTextContent('github');

    // Blocked tools section
    expect(screen.getByTestId('blocked-tools-section')).toBeInTheDocument();
    expect(screen.getByText('postgres/drop_database')).toBeInTheDocument();
    expect(screen.getByText('aws/terminate_instance')).toBeInTheDocument();
    expect(screen.getByText('Tool not in allowlist for server postgres')).toBeInTheDocument();

    // Allowed tools section
    expect(screen.getByTestId('allowed-tools-section')).toBeInTheDocument();
    expect(screen.getByText('github/create_issue')).toBeInTheDocument();
    expect(screen.getByText('github/read_repo')).toBeInTheDocument();

    // Collapse again
    fireEvent.click(toggleBtn);
    expect(screen.queryByTestId('scope-details-section')).not.toBeInTheDocument();
  });
});
