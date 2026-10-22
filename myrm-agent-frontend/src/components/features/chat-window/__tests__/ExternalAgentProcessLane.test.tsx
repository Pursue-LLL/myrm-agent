'use client';

/**
 * [INPUT]: ExternalAgentProcessLane.tsx 与 mock 外部 CLI Agent 配置/凭证数据
 * [OUTPUT]: 验证外部 CLI 进程通道渲染、状态徽章、任务派发交互、凭证与日志查看、以及折叠关闭行为
 * [POS]: myrm-agent-frontend/src/components/features/chat-window/__tests__/ExternalAgentProcessLane.test.tsx
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  ExternalAgentProcessLane,
  ExternalAgentConfigData,
  ProcessReceiptData,
} from '../ExternalAgentProcessLane';

const mockConfig: ExternalAgentConfigData = {
  agent_id: 'claude-lane-01',
  name: 'Claude Code Agent',
  kind: 'claude-code',
  command: 'claude',
  args: ['--non-interactive', '--json'],
  timeout_seconds: 45,
  expected_model: 'claude-3-7-sonnet',
};

const mockReceipts: ProcessReceiptData[] = [
  {
    execution_id: 'exec-alpha-001',
    agent_id: 'claude-lane-01',
    kind: 'claude-code',
    status: 'completed',
    exit_code: 0,
    duration_ms: 320,
    stdout_summary: 'Task executed successfully: build passed.',
    stderr_summary: '',
    receipt_hash: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
  },
  {
    execution_id: 'exec-alpha-002',
    agent_id: 'claude-lane-01',
    kind: 'claude-code',
    status: 'failed',
    exit_code: 1,
    duration_ms: 120,
    stdout_summary: '',
    stderr_summary: 'Error: invalid command argument.',
    receipt_hash: 'ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb',
  },
];

describe('ExternalAgentProcessLane', () => {
  it('renders lane header, kind badge, command, and model metadata', () => {
    render(<ExternalAgentProcessLane config={mockConfig} receipts={[]} />);

    expect(screen.getByText('Claude Code Agent')).toBeInTheDocument();
    expect(screen.getByText('claude-code')).toBeInTheDocument();
    expect(screen.getByText(/claude --non-interactive --json/)).toBeInTheDocument();
    expect(screen.getByText(/Model: claude-3-7-sonnet/)).toBeInTheDocument();
    expect(screen.getByText(/Timeout: 45s/)).toBeInTheDocument();
    expect(screen.getByText('Idle')).toBeInTheDocument();
  });

  it('renders latest receipt status and hash verification', () => {
    render(<ExternalAgentProcessLane config={mockConfig} receipts={mockReceipts} />);

    // Latest receipt in mockReceipts is failed
    expect(screen.getByText('failed')).toBeInTheDocument();
    expect(screen.getByText(/Receipt Hash:/)).toBeInTheDocument();
    expect(screen.getByText(/ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb/)).toBeInTheDocument();
    expect(screen.getByText('Error: invalid command argument.')).toBeInTheDocument();
  });

  it('triggers onExecute when input is typed and Run button is clicked', () => {
    const handleExecute = vi.fn();
    render(
      <ExternalAgentProcessLane
        config={mockConfig}
        receipts={[]}
        onExecute={handleExecute}
      />
    );

    const input = screen.getByPlaceholderText(/Dispatch instruction or input to CLI agent/);
    fireEvent.change(input, { target: { value: 'Fix linting errors in auth.ts' } });

    const runBtn = screen.getByRole('button', { name: /Run/ });
    fireEvent.click(runBtn);

    expect(handleExecute).toHaveBeenCalledTimes(1);
    expect(handleExecute).toHaveBeenCalledWith('Fix linting errors in auth.ts');
  });

  it('triggers onExecute on Enter key press in input field', () => {
    const handleExecute = vi.fn();
    render(
      <ExternalAgentProcessLane
        config={mockConfig}
        receipts={[]}
        onExecute={handleExecute}
      />
    );

    const input = screen.getByPlaceholderText(/Dispatch instruction or input to CLI agent/);
    fireEvent.change(input, { target: { value: 'Run test suite' } });
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });

    expect(handleExecute).toHaveBeenCalledWith('Run test suite');
  });

  it('switches receipt selection and displays stdout/stderr accordingly', () => {
    render(<ExternalAgentProcessLane config={mockConfig} receipts={mockReceipts} />);

    const select = screen.getByLabelText('Select execution receipt');
    expect(select).toBeInTheDocument();

    // Switch to first receipt
    fireEvent.change(select, { target: { value: 'exec-alpha-001' } });

    expect(screen.getByText('Task executed successfully: build passed.')).toBeInTheDocument();
    expect(screen.getByText(/e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855/)).toBeInTheDocument();
  });

  it('toggles collapse and close when buttons are clicked', () => {
    const handleDismiss = vi.fn();
    render(
      <ExternalAgentProcessLane
        config={mockConfig}
        receipts={mockReceipts}
        onDismiss={handleDismiss}
      />
    );

    // Initial expanded state displays input
    expect(screen.getByPlaceholderText(/Dispatch instruction or input to CLI agent/)).toBeInTheDocument();

    // Click collapse
    const collapseBtn = screen.getByLabelText('Collapse lane');
    fireEvent.click(collapseBtn);

    // Input should be hidden
    expect(screen.queryByPlaceholderText(/Dispatch instruction or input to CLI agent/)).not.toBeInTheDocument();

    // Click close
    const closeBtn = screen.getByLabelText('Close process lane');
    fireEvent.click(closeBtn);
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });
});
