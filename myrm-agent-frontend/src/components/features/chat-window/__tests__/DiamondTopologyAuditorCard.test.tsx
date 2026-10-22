import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { DiamondTopologyAuditorCard } from '../DiamondTopologyAuditorCard';
import { DEFAULT_DIAMOND_NODES } from '../diamond-graph/types';

describe('DiamondTopologyAuditorCard', () => {
  it('renders header, stages tab, and default 3-tier diamond nodes', () => {
    render(<DiamondTopologyAuditorCard chatId="chat-test-diamond-fe" />);

    expect(
      screen.getByRole('region', {
        name: /Diamond Topology and Adversarial Auditor/i,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText('chat-test-diamond-fe')).toBeInTheDocument();

    // Verify 3 stages
    expect(screen.getByText(/Stage 1: Fan-Out Exploration/i)).toBeInTheDocument();
    expect(screen.getByText(/Stage 2: Deterministic Reduce/i)).toBeInTheDocument();
    expect(screen.getByText(/Stage 3: Top-Tier Synthesis/i)).toBeInTheDocument();

    // Verify specific nodes
    expect(screen.getByText('Explore Qdrant Vector Engine')).toBeInTheDocument();
    expect(screen.getByText('Deterministic Map-Reduce Deduplicator')).toBeInTheDocument();
    expect(screen.getByText('Top-Tier High Quality Synthesis')).toBeInTheDocument();
  });

  it('prunes false dependencies between parallel branches', async () => {
    const handlePrune = vi.fn().mockResolvedValue([['fan-worker-1', 'fan-worker-2']]);

    render(
      <DiamondTopologyAuditorCard
        chatId="chat-test-diamond-fe"
        onPruneDependencies={handlePrune}
      />,
    );

    const pruneBtn = screen.getByRole('button', { name: /Prune False Deps/i });
    fireEvent.click(pruneBtn);

    expect(handlePrune).toHaveBeenCalled();
    expect(
      await screen.findByText(/Pruned artificial serialized dependencies successfully/i),
    ).toBeInTheDocument();
  });

  it('switches to Census Sentinel tab and displays dispatch metrics', () => {
    render(<DiamondTopologyAuditorCard chatId="chat-test-diamond-fe" />);

    const censusTab = screen.getByRole('button', { name: /Census Sentinel/i });
    fireEvent.click(censusTab);

    expect(screen.getByText('Dead-Node Census Sentinel Status')).toBeInTheDocument();
    expect(screen.getByText('Healthy (No Dead Nodes)')).toBeInTheDocument();
    expect(screen.getByText('Dispatched')).toBeInTheDocument();
    expect(screen.getByText('Received')).toBeInTheDocument();
  });

  it('retries dead nodes when imbalance exists in census tab', async () => {
    const uncompletedNodes = [
      ...DEFAULT_DIAMOND_NODES.slice(0, 2),
      {
        ...DEFAULT_DIAMOND_NODES[2],
        status: 'pending',
      },
      ...DEFAULT_DIAMOND_NODES.slice(3),
    ];

    const handleRetry = vi.fn().mockResolvedValue(['fan-worker-3']);

    render(
      <DiamondTopologyAuditorCard
        chatId="chat-test-diamond-fe"
        initialNodes={uncompletedNodes}
        onRetryDeadNodes={handleRetry}
      />,
    );

    const censusTab = screen.getByRole('button', { name: /Census Sentinel/i });
    fireEvent.click(censusTab);

    expect(screen.getByText('Imbalance Detected')).toBeInTheDocument();
    const retryBtn = screen.getByRole('button', { name: /Retry Dead Nodes/i });
    fireEvent.click(retryBtn);

    expect(handleRetry).toHaveBeenCalled();
    expect(await screen.findByText(/Retried 1 nodes successfully/i)).toBeInTheDocument();
  });

  it('switches to Blinded Panel tab and displays 3 independent perspectives and reality anchors', () => {
    render(<DiamondTopologyAuditorCard chatId="chat-test-diamond-fe" />);

    const auditTab = screen.getByRole('button', { name: /Blinded Panel & Anchors/i });
    fireEvent.click(auditTab);

    // Consensus verdict
    expect(screen.getByText(/VERDICT: PASSED/i)).toBeInTheDocument();
    expect(screen.getByText('3/3 Approved')).toBeInTheDocument();

    // 3 perspectives
    expect(screen.getByText(/FACT ACCURACY/i)).toBeInTheDocument();
    expect(screen.getByText(/TIMELINESS/i)).toBeInTheDocument();
    expect(screen.getByText(/CITATION AUTHORITY/i)).toBeInTheDocument();
    expect(screen.getAllByText(/✓ Strict Context Isolation/i).length).toBe(3);

    // Objective reality anchors
    expect(screen.getByText(/\[exit_code_zero\] pytest_suite/i)).toBeInTheDocument();
    expect(screen.getByText(/\[hash_match\] sha256_bundle/i)).toBeInTheDocument();
    expect(screen.getAllByText('MATCH').length).toBe(2);
  });

  it('triggers blinded audit execution via button', async () => {
    const handleRunAudit = vi.fn().mockResolvedValue({
      passed: true,
      totalReviews: 3,
      passCount: 3,
      consensusSummary: 'Fresh audit passed unanimously.',
      timestamp: Date.now(),
      reviews: [],
      anchorChecks: [],
    });

    render(
      <DiamondTopologyAuditorCard
        chatId="chat-test-diamond-fe"
        onRunAudit={handleRunAudit}
      />,
    );

    const runBtn = screen.getByRole('button', { name: /Run Blind Audit/i });
    fireEvent.click(runBtn);

    expect(handleRunAudit).toHaveBeenCalled();
    expect(
      await screen.findByText(/Audit completed with objective reality checks/i),
    ).toBeInTheDocument();
  });
});
