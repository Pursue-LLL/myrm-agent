/** @vitest-environment jsdom */

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { RuntimeConsoleDrawer } from '../RuntimeConsoleDrawer';

const stableT = (key: string) => {
  const table: Record<string, string> = {
    title: '运行时控制台与多端状态投影中枢',
    mateclawParity: '对标 MateClaw 纯函数式投影架构 · View = Project(RunState, Events)',
    'attemptInspector.title': 'Attempt 状态机变迁与吞吐水位线',
    'deliverablesSection.title': '产出工件与事实矩阵',
    'auditSection.title': '合规安全与权限决策流水',
    tokensTotal: '累计消耗 Tokens',
    avgThroughput: '平均生成速率',
    closeDrawer: '关闭控制台',
  };
  return table[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('RuntimeConsoleDrawer', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders nothing when isOpen is false', () => {
    const { container } = render(
      <RuntimeConsoleDrawer runId="run_mateclaw_demo_001" isOpen={false} onClose={vi.fn()} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders drawer header, MateClaw parity badge, and telemetry watermark', async () => {
    render(<RuntimeConsoleDrawer runId="run_mateclaw_demo_001" isOpen={true} onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('Enterprise Microservice State Projection Refactor')).toBeInTheDocument();
    });

    expect(screen.getByText('MateClaw Parity')).toBeInTheDocument();
    expect(screen.getByText(/对标 MateClaw 纯函数式投影架构/i)).toBeInTheDocument();
    expect(screen.getByText(/5970/i)).toBeInTheDocument();
    expect(screen.getByText(/平均生成速率/i)).toBeInTheDocument();
  });

  it('displays attempt waterfall and allows expanding fault diagnostic in runtime console', async () => {
    render(<RuntimeConsoleDrawer runId="run_mateclaw_demo_001" isOpen={true} onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('Attempt #1')).toBeInTheDocument();
      expect(screen.getByText('Attempt #2')).toBeInTheDocument();
    });

    // Attempt #1 is failed by default and expanded
    expect(screen.getByText(/Fault Diagnostic Reason:/i)).toBeInTheDocument();
    expect(screen.getByText(/ProviderRateLimitError: 429/i)).toBeInTheDocument();

    // Attempt #2 throughput rate
    expect(screen.getByText(/223.1 tok\/s/i)).toBeInTheDocument();
  });

  it('switches surface to deliverables and renders artifact matrix', async () => {
    render(<RuntimeConsoleDrawer runId="run_mateclaw_demo_001" isOpen={true} onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('Enterprise Microservice State Projection Refactor')).toBeInTheDocument();
    });

    const deliverablesTab = screen.getByRole('tab', { name: /Deliverables/i });
    fireEvent.click(deliverablesTab);

    await waitFor(() => {
      expect(screen.getByText('产出工件与事实矩阵')).toBeInTheDocument();
    });

    expect(screen.getByText('Async Event Stream Projection Engine')).toBeInTheDocument();
    expect(screen.getByText('src/components/features/runtime/useRunProjection.ts')).toBeInTheDocument();
  });

  it('switches surface to audit ledger and renders compliance decisions', async () => {
    render(<RuntimeConsoleDrawer runId="run_mateclaw_demo_001" isOpen={true} onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('Enterprise Microservice State Projection Refactor')).toBeInTheDocument();
    });

    const auditTab = screen.getByRole('tab', { name: /Audit Ledger/i });
    fireEvent.click(auditTab);

    await waitFor(() => {
      expect(screen.getByText('合规安全与权限决策流水')).toBeInTheDocument();
    });

    expect(screen.getByText('file_mutation')).toBeInTheDocument();
    expect(screen.getByText('Actor: myrm_agent_runtime')).toBeInTheDocument();
    expect(screen.getByText('approved')).toBeInTheDocument();
  });

  it('triggers onClose when clicking close button', async () => {
    const handleClose = vi.fn();
    render(<RuntimeConsoleDrawer runId="run_mateclaw_demo_001" isOpen={true} onClose={handleClose} />);

    await waitFor(() => {
      expect(screen.getByLabelText('关闭控制台')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText('关闭控制台'));
    expect(handleClose).toHaveBeenCalledTimes(1);
  });
});
