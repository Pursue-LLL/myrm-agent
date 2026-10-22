'use client';

/**
 * [INPUT]: DebateTradeoffMatrixCard.tsx 与 mock 权衡对比矩阵数据
 * [OUTPUT]: 验证决策权衡对比矩阵渲染、Leader 推荐理由与一键采纳、方案 Tab 切换、多维度打分与折叠关闭行为
 * [POS]: myrm-agent-frontend/src/components/features/chat-window/__tests__/DebateTradeoffMatrixCard.test.tsx
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  DebateTradeoffMatrixCard,
  TradeoffMatrixData,
} from '../DebateTradeoffMatrixCard';

const mockMatrix: TradeoffMatrixData = {
  matrix_id: 'matrix-alpha-101',
  workflow_id: 'wf-consult-001',
  topic: 'Select Primary RPC Protocol: gRPC vs tRPC vs REST',
  dimensions: [
    'performance',
    'cost_efficiency',
    'implementation_complexity',
    'reliability',
    'maintainability',
  ],
  dimension_weights: {
    performance: 0.25,
    cost_efficiency: 0.2,
    implementation_complexity: 0.2,
    reliability: 0.2,
    maintainability: 0.15,
  },
  winner_proposal_id: 'prop-grpc',
  recommendation_rationale:
    'gRPC selected as the enterprise standard due to exceptional streaming performance and cross-language schema enforcement.',
  proposals: [
    {
      proposal_id: 'prop-grpc',
      title: 'HTTP/2 Protobuf gRPC Engine',
      author_role: 'research_analyst',
      author_agent_id: 'agent-researcher-01',
      summary: 'High-performance binary streaming RPC with strict proto contract generation.',
      pros: ['Sub-millisecond latency', 'Bidirectional streaming', 'Cross-language SDKs'],
      cons: ['Requires HTTP/2 load balancer support', 'Difficult browser debugging'],
      dimension_scores: {
        performance: 0.95,
        cost_efficiency: 0.85,
        implementation_complexity: 0.65,
        reliability: 0.95,
        maintainability: 0.88,
      },
      is_recommended: true,
    },
    {
      proposal_id: 'prop-trpc',
      title: 'End-to-End Type-Safe tRPC Router',
      author_role: 'feasibility_auditor',
      author_agent_id: 'agent-auditor-02',
      summary: 'Lightweight JSON RPC router tightly coupled to TypeScript AST.',
      pros: ['Zero schema compilation step', 'Fastest frontend developer velocity'],
      cons: ['TypeScript-only tight coupling', 'No native non-node microservices support'],
      dimension_scores: {
        performance: 0.78,
        cost_efficiency: 0.92,
        implementation_complexity: 0.9,
        reliability: 0.82,
        maintainability: 0.85,
      },
      is_recommended: false,
    },
  ],
};

describe('DebateTradeoffMatrixCard', () => {
  it('renders matrix header, topic, and proposals evaluated badge', () => {
    render(<DebateTradeoffMatrixCard matrix={mockMatrix} />);

    expect(screen.getByText('Decision Trade-off Matrix')).toBeInTheDocument();
    expect(screen.getByText('2 Proposals Evaluated')).toBeInTheDocument();
    expect(screen.getByText(/Select Primary RPC Protocol/)).toBeInTheDocument();
  });

  it('renders leader recommendation rationale and winner banner', () => {
    render(<DebateTradeoffMatrixCard matrix={mockMatrix} />);

    expect(screen.getByText('Leader Consensus Recommendation')).toBeInTheDocument();
    expect(screen.getByText(/gRPC selected as the enterprise standard/)).toBeInTheDocument();
    expect(screen.getByText('Winner')).toBeInTheDocument();
  });

  it('triggers onAdopt callback with winning proposal ID when adopt button is clicked', () => {
    const handleAdopt = vi.fn();
    render(<DebateTradeoffMatrixCard matrix={mockMatrix} onAdopt={handleAdopt} />);

    const adoptBtn = screen.getByRole('button', { name: /Adopt Solution/ });
    fireEvent.click(adoptBtn);

    expect(handleAdopt).toHaveBeenCalledTimes(1);
    expect(handleAdopt).toHaveBeenCalledWith('prop-grpc');
  });

  it('switches active proposal tab and displays corresponding pros, cons, and scores', () => {
    render(<DebateTradeoffMatrixCard matrix={mockMatrix} />);

    // Switch to tRPC proposal
    const trpcTab = screen.getByText('End-to-End Type-Safe tRPC Router');
    fireEvent.click(trpcTab);

    expect(
      screen.getByText(/Lightweight JSON RPC router tightly coupled to TypeScript AST/)
    ).toBeInTheDocument();
    expect(screen.getByText('Zero schema compilation step')).toBeInTheDocument();
    expect(screen.getByText('TypeScript-only tight coupling')).toBeInTheDocument();

    // Verify dimension score percentage
    expect(screen.getByText('Performance')).toBeInTheDocument();
    expect(screen.getByText('78%')).toBeInTheDocument();
  });

  it('collapses and expands matrix when toggle button is clicked', () => {
    render(<DebateTradeoffMatrixCard matrix={mockMatrix} />);

    // Initially expanded
    expect(screen.getByText('Leader Consensus Recommendation')).toBeInTheDocument();

    // Click collapse
    const collapseBtn = screen.getByLabelText('Collapse matrix');
    fireEvent.click(collapseBtn);

    // Content hidden
    expect(screen.queryByText('Leader Consensus Recommendation')).not.toBeInTheDocument();

    // Click expand
    const expandBtn = screen.getByLabelText('Expand matrix');
    fireEvent.click(expandBtn);

    // Content reappears
    expect(screen.getByText('Leader Consensus Recommendation')).toBeInTheDocument();
  });

  it('triggers onDismiss callback when close button is clicked', () => {
    const handleDismiss = vi.fn();
    render(<DebateTradeoffMatrixCard matrix={mockMatrix} onDismiss={handleDismiss} />);

    const closeBtn = screen.getByLabelText('Close matrix card');
    fireEvent.click(closeBtn);

    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });
});
