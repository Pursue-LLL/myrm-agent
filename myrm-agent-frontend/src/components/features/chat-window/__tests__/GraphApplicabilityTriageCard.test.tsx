import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { GraphApplicabilityTriageCard } from '../GraphApplicabilityTriageCard';

describe('GraphApplicabilityTriageCard', () => {
  it('renders card header, triage banner, budget gauge, and accessible live output', () => {
    render(<GraphApplicabilityTriageCard />);

    // 1. Header & Title
    expect(
      screen.getByTestId('graph-applicability-triage-card'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('GraphApplicabilityTriageGateAndElasticBudgetCircuitBreakerPack'),
    ).toBeInTheDocument();
    expect(screen.getByText('P0 核心经济性治理')).toBeInTheDocument();

    // 2. Initial Triage Decision (Admit)
    const verdictBadge = screen.getByTestId('triage-verdict-badge');
    expect(verdictBadge).toHaveTextContent('准许进入图工程 (ADMIT)');

    // 3. Initial Budget Guard Status
    const budgetBadge = screen.getByTestId('budget-guard-status-badge');
    expect(budgetBadge).toHaveTextContent('预算充裕准许扇出');

    // 4. Accessible Output
    const liveOutput = screen.getByTestId('graph-triage-status-live');
    expect(liveOutput).toHaveTextContent('图工程自适应准入门禁与预算熔断防护网已就绪。');
  });

  it('toggles between different triage scenarios: simple, exploratory, sequential, and parallel', () => {
    render(<GraphApplicabilityTriageCard />);

    // Scenario 1: Simple single-step typo fix (Reject -> Single Agent)
    fireEvent.click(screen.getByTestId('scenario-simple-btn'));
    expect(screen.getByTestId('triage-verdict-badge')).toHaveTextContent(
      '拦截并降级为单 Agent (REJECT)',
    );
    expect(
      screen.getByText(/任务属于单步操作（如错别字修复）/i),
    ).toBeInTheDocument();
    expect(screen.getByText('45,000 Tokens')).toBeInTheDocument();

    // Scenario 2: Exploratory conversation (Reject -> Conversational)
    fireEvent.click(screen.getByTestId('scenario-exploratory-btn'));
    expect(screen.getByTestId('triage-verdict-badge')).toHaveTextContent(
      '拦截并保持交互对话 (REJECT)',
    );
    expect(
      screen.getByText(/任务属于未定型探索性头脑风暴或人机互动对话/i),
    ).toBeInTheDocument();

    // Scenario 3: Strictly sequential (Reject -> Linear Pipeline)
    fireEvent.click(screen.getByTestId('scenario-sequential-btn'));
    expect(screen.getByTestId('triage-verdict-badge')).toHaveTextContent(
      '拦截并保持线性流水线 (REJECT)',
    );
    expect(
      screen.getByText(/所有子任务具备强因果时序依赖链条/i),
    ).toBeInTheDocument();

    // Scenario 4: Heavyweight parallel (Admit -> Graph)
    fireEvent.click(screen.getByTestId('scenario-parallel-btn'));
    expect(screen.getByTestId('triage-verdict-badge')).toHaveTextContent(
      '准许进入图工程 (ADMIT)',
    );
  });

  it('updates predictive budget calculation and simulates massive over-cap fanout', () => {
    render(<GraphApplicabilityTriageCard />);

    // 1. Initial prediction
    expect(screen.getByTestId('predicted-tokens-val')).toBeInTheDocument();
    expect(screen.getByTestId('budget-guard-status-badge')).toHaveTextContent('预算充裕准许扇出');

    // 2. Click simulate massive fanout
    fireEvent.click(screen.getByTestId('simulate-massive-fanout-btn'));

    // Should trigger circuit breaker
    expect(screen.getByTestId('budget-guard-status-badge')).toHaveTextContent('硬上限熔断拦截');
    expect(screen.getByTestId('predicted-tokens-val')).toHaveTextContent('205,000');
    expect(screen.getByTestId('budget-recommendation-text')).toHaveTextContent(
      'INTERCEPT: 预估 205,000 Tokens 超出 100,000 硬上限',
    );
    expect(screen.getByTestId('graph-triage-status-live')).toHaveTextContent(
      '警报：模拟 16 节点重型扇出超出硬上限，图工程熔断门禁成功拦截！',
    );
  });

  it('simulates dynamic spend levels from healthy to warning, critical, and exhausted with concurrency throttling', () => {
    render(<GraphApplicabilityTriageCard />);

    // 1. Simulate Warning Step (25% remaining)
    fireEvent.click(screen.getByTestId('simulate-warning-step-btn'));
    expect(screen.getByTestId('live-spend-status-badge')).toHaveTextContent(
      '预警节流 (WARNING <30%)',
    );
    expect(screen.getByTestId('remaining-pct-val')).toHaveTextContent('25%');
    expect(screen.getByTestId('active-concurrency-val')).toHaveTextContent('2 路');
    expect(screen.getByTestId('is-throttled-val')).toHaveTextContent('已触发自适应降速');

    // 2. Simulate Critical Step (8% remaining)
    fireEvent.click(screen.getByTestId('simulate-critical-step-btn'));
    expect(screen.getByTestId('live-spend-status-badge')).toHaveTextContent(
      '危急降级 (CRITICAL <10%)',
    );
    expect(screen.getByTestId('remaining-pct-val')).toHaveTextContent('8%');
    expect(screen.getByTestId('active-concurrency-val')).toHaveTextContent('1 路');

    // 3. Simulate Exhausted Step (0% remaining -> circuit broken)
    fireEvent.click(screen.getByTestId('simulate-exhausted-step-btn'));
    expect(screen.getByTestId('live-spend-status-badge')).toHaveTextContent(
      '额度耗尽熔断 (EXHAUSTED)',
    );
    expect(screen.getByTestId('remaining-pct-val')).toHaveTextContent('0%');
    expect(screen.getByTestId('active-concurrency-val')).toHaveTextContent('0 路');
    expect(screen.getByTestId('is-circuit-broken-val')).toHaveTextContent('已触发强行熔断');

    // 4. Return to Healthy Step (80% remaining)
    fireEvent.click(screen.getByTestId('simulate-healthy-step-btn'));
    expect(screen.getByTestId('live-spend-status-badge')).toHaveTextContent(
      '健康充裕 (HEALTHY)',
    );
    expect(screen.getByTestId('active-concurrency-val')).toHaveTextContent('4 路');
  });

  it('triggers graceful partial early reduce and inspects salvaged deliverables dialog', () => {
    render(<GraphApplicabilityTriageCard />);

    // 1. Move to critical spend
    fireEvent.click(screen.getByTestId('simulate-critical-step-btn'));

    // 2. Trigger early reduce
    fireEvent.click(screen.getByTestId('trigger-early-reduce-btn'));

    // 3. Verify reduce dialog is open
    expect(
      screen.getByRole('dialog', { name: /提前局部优雅归约报告/i }),
    ).toBeInTheDocument();
    expect(screen.getByTestId('reduce-report-summary')).toHaveTextContent(
      'Graceful Early Reduce Triggered (CRITICAL)',
    );
    expect(screen.getByText('2 个')).toBeInTheDocument();
    expect(
      screen.getByText(/已跳过后续 2 个待执行节点，保全成果成功交付。/i),
    ).toBeInTheDocument();

    // 4. Close dialog
    fireEvent.click(screen.getByTestId('close-reduce-dialog-btn'));
    expect(
      screen.queryByRole('dialog', { name: /提前局部优雅归约报告/i }),
    ).not.toBeInTheDocument();
  });
});
