'use client';

/**
 * [INPUT]: AgentOwnedOperationsDrawer.tsx 与 mock 花名册数据
 * [OUTPUT]: 验证 Agent-Owned 多智能体协同操作抽屉渲染、Roster 切换、能力解析探针与专属隔离错误栈交互
 * [POS]: myrm-agent-frontend/src/components/features/chat-window/__tests__/AgentOwnedOperationsDrawer.test.tsx
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  AgentOwnedOperationsDrawer,
  AgentRosterEntryItem,
} from '../AgentOwnedOperationsDrawer';

const mockRoster: AgentRosterEntryItem[] = [
  {
    agentId: 'worker_coder',
    role: 'code_implementer',
    providerModel: 'deepseek/deepseek-coder',
    capabilities: ['write_code', 'run_tests'],
    allowlist: ['tool_fs_write', 'tool_run_tests'],
    errorCount: 0,
    isHealthy: true,
    errorStack: [],
  },
  {
    agentId: 'worker_reviewer',
    role: 'code_reviewer',
    providerModel: 'anthropic/claude-3-5-sonnet',
    capabilities: ['review_diff'],
    allowlist: ['tool_read_diff'],
    errorCount: 1,
    isHealthy: false,
    errorStack: [
      {
        errorId: 'err_001',
        operation: 'inspect_git_diff',
        errorType: 'TimeoutError',
        message: 'Diff generation exceeded 30s timeout limit',
        fatal: true,
      },
    ],
  },
];

describe('AgentOwnedOperationsDrawer', () => {
  it('returns null when isOpen is false', () => {
    const { container } = render(
      <AgentOwnedOperationsDrawer isOpen={false} onClose={vi.fn()} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders header, session tag, and triggers onClose when close button clicked', () => {
    const handleClose = vi.fn();
    render(
      <AgentOwnedOperationsDrawer
        isOpen={true}
        onClose={handleClose}
        sessionId="chat_test_123"
        roster={mockRoster}
      />
    );

    expect(screen.getByTestId('agent-owned-operations-drawer')).toBeInTheDocument();
    expect(screen.getByText('Agent-Owned Operations Fabric')).toBeInTheDocument();
    expect(screen.getByText('session: chat_test_123')).toBeInTheDocument();

    const closeBtn = screen.getByTestId('close-drawer-btn');
    fireEvent.click(closeBtn);
    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it('renders list-form roster and switches active agent selection', () => {
    render(
      <AgentOwnedOperationsDrawer
        isOpen={true}
        onClose={vi.fn()}
        roster={mockRoster}
      />
    );

    // Initial selected is worker_coder
    expect(screen.getByTestId('roster-item-worker_coder')).toBeInTheDocument();
    expect(screen.getByTestId('roster-item-worker_reviewer')).toBeInTheDocument();
    expect(screen.getByText('Healthy')).toBeInTheDocument();
    expect(screen.getByText('1 Err')).toBeInTheDocument();

    // Click on worker_reviewer
    fireEvent.click(screen.getByTestId('roster-item-worker_reviewer'));

    // Should display worker_reviewer's owned provider setup and isolated error
    expect(screen.getAllByText('anthropic/claude-3-5-sonnet').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByTestId('error-item-err_001')).toBeInTheDocument();
    expect(screen.getByText('TimeoutError in inspect_git_diff')).toBeInTheDocument();
  });

  it('probes capability alignment against active agent allowlist', async () => {
    render(
      <AgentOwnedOperationsDrawer
        isOpen={true}
        onClose={vi.fn()}
        roster={mockRoster}
      />
    );

    const input = screen.getByTestId('probe-input');
    const testBtn = screen.getByTestId('probe-test-btn');

    // 1. Test allowed tool for worker_coder
    fireEvent.change(input, { target: { value: 'tool_fs_write' } });
    fireEvent.click(testBtn);

    expect(screen.getByTestId('probe-verdict')).toHaveTextContent(
      'Capability permitted under agent allowlist'
    );

    // 2. Test disallowed tool
    fireEvent.change(input, { target: { value: 'tool_drop_db' } });
    fireEvent.click(testBtn);

    expect(screen.getByTestId('probe-verdict')).toHaveTextContent(
      'Disallowed: Target not in agent allowlist'
    );
  });

  it('triggers onClearErrors when clear button is clicked for agent with errors', () => {
    const handleClear = vi.fn();
    render(
      <AgentOwnedOperationsDrawer
        isOpen={true}
        onClose={vi.fn()}
        roster={mockRoster}
        onClearErrors={handleClear}
      />
    );

    // Switch to worker_reviewer
    fireEvent.click(screen.getByTestId('roster-item-worker_reviewer'));

    const clearBtn = screen.getByTestId('clear-errors-btn');
    fireEvent.click(clearBtn);

    expect(handleClear).toHaveBeenCalledWith('worker_reviewer');
  });
});
