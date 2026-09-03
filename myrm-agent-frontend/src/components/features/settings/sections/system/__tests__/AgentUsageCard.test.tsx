/** @vitest-environment jsdom */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import AgentUsageCard from '../AgentUsageCard';
import { getAgentUsage } from '@/services/statistics';

const stableT = (key: string, params?: Record<string, unknown>) => {
  if (params?.count !== undefined) return `Count: ${params.count}`;
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

vi.mock('@/services/statistics', () => ({
  getAgentUsage: vi.fn(),
}));

describe('AgentUsageCard', () => {
  const mockSingleAgent = {
    agents: [
      {
        agentId: 'agent-solitary',
        name: 'Solitary Assistant',
        avatar: null,
        totalTokens: 1500,
        totalUsd: 0.075,
        totalCalls: 12,
        sessions: 4,
        percentTokens: 100,
        percentUsd: 100,
        sparkline: [
          { date: '2026-06-01', tokens: 100, usd: 0.005 },
          { date: '2026-06-02', tokens: 200, usd: 0.01 },
        ],
        attribution: {
          webUsd: 0.05,
          cronUsd: 0.015,
          channelUsd: 0.0,
          subagentsUsd: 0.01,
          webTokens: 1000,
          cronTokens: 300,
          channelTokens: 0,
          subagentsTokens: 200,
        },
      },
    ],
    total_agents: 1,
    grand_total_tokens: 1500,
    grand_total_usd: 0.075,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders correctly for a single agent profile without hiding', async () => {
    (getAgentUsage as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(mockSingleAgent);

    render(<AgentUsageCard />);

    await waitFor(() => {
      expect(screen.getByText('Solitary Assistant')).toBeInTheDocument();
    });

    expect(screen.getByText('100%')).toBeInTheDocument();
  });

  it('toggles why-spent attribution breakdown on click', async () => {
    (getAgentUsage as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(mockSingleAgent);

    render(<AgentUsageCard />);

    await waitFor(() => {
      expect(screen.getByText('Solitary Assistant')).toBeInTheDocument();
    });

    const toggleBtn = screen.getByTestId('toggle-why-spent-agent-solitary');
    expect(toggleBtn).toBeInTheDocument();

    fireEvent.click(toggleBtn);

    await waitFor(() => {
      expect(screen.getByText('sourceWeb')).toBeInTheDocument();
      expect(screen.getByText('sourceSubagents')).toBeInTheDocument();
      expect(screen.getByText('sourceCron')).toBeInTheDocument();
      expect(screen.getByText('sourceChannel')).toBeInTheDocument();
    });
  });
});
