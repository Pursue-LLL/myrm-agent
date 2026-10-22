import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AgenticTrafficDeck } from '../AgenticTrafficDeck';
import { AbandonmentAttributionView } from '../AbandonmentAttributionView';
import type { AgentTrafficSummaryData, AeoPageDiagnosticData } from '../agenticTrafficTypes';

describe('AgenticTrafficDeck & AbandonmentAttributionView', () => {
  const mockSummary: AgentTrafficSummaryData = {
    total_visits: 120,
    agent_visits_count: 85,
    human_visits_count: 35,
    agent_traffic_ratio_pct: 70.83,
    top_agents: {
      CURSOR: 45,
      CLAUDE_CODE: 25,
      WINDSURF: 10,
      OPENCLAW: 5,
    },
    funnel_conversion: {
      DISCOVERED: 85,
      CONTEXT_ABSORBED: 52,
      SANDBOX_PROBED: 28,
      ADOPTED: 15,
    },
    abandonment_distribution: {
      LLMS_TXT_MISSING: 18,
      FIRST_500_TOKENS_VAGUE: 12,
      TOKEN_OVERFLOW_20K: 7,
    },
    recent_visits: [
      {
        visit_id: 'v-01',
        agent_type: 'CURSOR',
        user_agent: 'Cursor/0.45.2',
        target_path: '/docs/quickstart',
        duration_ms: 410.0,
        status_code: 200,
        is_agent: true,
        confidence_score: 0.95,
        funnel_stage: 'CONTEXT_ABSORBED',
        abandonment_reasons: ['NONE'],
        timestamp: '2026-10-12T10:00:00Z',
      },
    ],
    generated_at: '2026-10-12T10:05:00Z',
  };

  const mockDiagnostic: AeoPageDiagnosticData = {
    path: '/docs/vague-doc',
    estimated_tokens: 3200,
    has_llms_txt_declared: false,
    has_code_in_first_500_tokens: false,
    is_spa_client_blank: false,
    suggested_actions: [
      '在根目录声明标准 /llms.txt',
      '在前 500 Token 提供可运行代码示例',
    ],
    abandonment_reasons: ['LLMS_TXT_MISSING', 'FIRST_500_TOKENS_VAGUE'],
    aeo_score: 50,
  };

  it('renders AgenticTrafficDeck with metrics, badges, and 4-tier funnel', () => {
    const handleRefresh = vi.fn();
    render(<AgenticTrafficDeck summary={mockSummary} onRefresh={handleRefresh} />);

    expect(screen.getByTestId('agentic-traffic-deck')).toBeInTheDocument();
    expect(screen.getByText(/AI 流量占比 70.83%/)).toBeInTheDocument();
    expect(screen.getByText('120')).toBeInTheDocument();
    expect(screen.getAllByText('85')).toHaveLength(2);
    expect(screen.getByText('35')).toBeInTheDocument();

    expect(screen.getByTestId('badge-CURSOR')).toHaveTextContent('45');
    expect(screen.getByTestId('badge-CLAUDE_CODE')).toHaveTextContent('25');

    expect(screen.getByTestId('funnel-step-DISCOVERED')).toBeInTheDocument();
    expect(screen.getByTestId('funnel-step-ADOPTED')).toBeInTheDocument();

    const refreshBtn = screen.getByTestId('refresh-traffic-btn');
    fireEvent.click(refreshBtn);
    expect(handleRefresh).toHaveBeenCalledTimes(1);
  });

  it('renders loading placeholder when summary is null', () => {
    render(<AgenticTrafficDeck summary={null} />);
    expect(screen.getByTestId('agentic-traffic-loading')).toBeInTheDocument();
  });

  it('renders AbandonmentAttributionView and executes interactive AEO diagnosis', async () => {
    const handleDiagnose = vi.fn().mockResolvedValue(mockDiagnostic);

    render(
      <AbandonmentAttributionView
        abandonmentDistribution={mockSummary.abandonment_distribution}
        onDiagnose={handleDiagnose}
      />
    );

    expect(screen.getByTestId('abandonment-attribution-view')).toBeInTheDocument();
    expect(screen.getByTestId('reason-card-LLMS_TXT_MISSING')).toHaveTextContent('18 次');
    expect(screen.getByTestId('reason-card-FIRST_500_TOKENS_VAGUE')).toHaveTextContent('12 次');

    // 输入内容并运行诊断
    const contentTextarea = screen.getByTestId('input-diagnostic-content');
    fireEvent.change(contentTextarea, { target: { value: '# Some vague doc text' } });

    const runBtn = screen.getByTestId('run-diagnosis-btn');
    fireEvent.click(runBtn);

    expect(handleDiagnose).toHaveBeenCalledWith(
      '/docs/quickstart',
      '# Some vague doc text',
      false
    );

    await waitFor(() => {
      expect(screen.getByTestId('aeo-result-card')).toBeInTheDocument();
      expect(screen.getByTestId('aeo-score-badge')).toHaveTextContent('50 / 100');
      expect(screen.getByText(/在根目录声明标准 \/llms\.txt/)).toBeInTheDocument();
    });
  });
});
