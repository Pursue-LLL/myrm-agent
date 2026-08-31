/** @vitest-environment jsdom */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { CouncilResultCard } from '../CouncilResultCard';
import type { CouncilResultView } from '@/store/chat/types/messages';

const stableT = (key: string, params?: Record<string, unknown>) => {
  if (params?.count !== undefined) {
    return `${key}:${params.count}`;
  }
  if (params?.round !== undefined) {
    return `${key}:${params.round}`;
  }
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('CouncilResultCard', () => {
  const mockCouncilResult: CouncilResultView = {
    success: true,
    synthesis: 'Final synthesized architecture: Microservices with event-driven queue.',
    consensus_points: ['Agreed on message queue decoupling', 'Agreed on PostgreSQL as SSOT'],
    divergences: ['Debate on Redis vs Memcached for L2 caching'],
    action_items: ['1. Deploy Kafka broker', '2. Refactor auth service to stateless JWT'],
    rounds_completed: 2,
    total_duration_seconds: 4.8,
    opinions: [
      {
        expert_id: 'arch-lead',
        agent_type: 'Principal Architect',
        round_num: 1,
        content: 'Recommend microservice decomposition for high scalability.',
        success: true,
        duration_seconds: 1.2,
      },
      {
        expert_id: 'sec-audit',
        agent_type: 'Security Auditor',
        round_num: 1,
        content: 'Ensure all inter-service communication is mTLS encrypted.',
        success: true,
        duration_seconds: 1.5,
      },
    ],
  };

  it('renders council synthesis, consensus, and action items', () => {
    render(<CouncilResultCard councilResult={mockCouncilResult} />);

    expect(screen.getByTestId('council-result-card')).toBeInTheDocument();
    expect(screen.getByText('councilResultTitle')).toBeInTheDocument();
    expect(
      screen.getByText('Final synthesized architecture: Microservices with event-driven queue.'),
    ).toBeInTheDocument();
    expect(screen.getByText('Agreed on message queue decoupling')).toBeInTheDocument();
    expect(screen.getByText('Debate on Redis vs Memcached for L2 caching')).toBeInTheDocument();
    expect(screen.getByText('1. Deploy Kafka broker')).toBeInTheDocument();
    expect(screen.getByText('4.8s')).toBeInTheDocument();
  });

  it('toggles expert opinions panel on click', async () => {
    render(<CouncilResultCard councilResult={mockCouncilResult} />);

    expect(screen.queryByText('Principal Architect')).not.toBeInTheDocument();

    const toggleBtn = screen.getByTestId('toggle-expert-opinions-btn');
    expect(toggleBtn).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(toggleBtn);
    });

    expect(screen.getByText('Principal Architect')).toBeInTheDocument();
    expect(screen.getByText('Security Auditor')).toBeInTheDocument();
    expect(
      screen.getByText('Recommend microservice decomposition for high scalability.'),
    ).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(toggleBtn);
    });

    expect(screen.queryByText('Principal Architect')).not.toBeInTheDocument();
  });
});
