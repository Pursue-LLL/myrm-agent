import { render, screen, fireEvent, within } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import {
  ConversationalSpecialistSummoningCard,
  SummonSessionExecutionData,
} from '../ConversationalSpecialistSummoningCard';

describe('ConversationalSpecialistSummoningCard', () => {
  it('renders initial empty state and handles dismiss', () => {
    const handleDismiss = vi.fn();
    render(
      <ConversationalSpecialistSummoningCard
        chatId="test-chat-01"
        onDismiss={handleDismiss}
      />
    );

    expect(screen.getByTestId('specialist-summoning-card')).toBeInTheDocument();
    expect(screen.getByTestId('stat-available-specialists')).toHaveTextContent('4');
    expect(screen.getByTestId('stat-summoned-count')).toHaveTextContent('0');
    expect(screen.getByTestId('stat-bridged-cards')).toHaveTextContent('0');
    expect(screen.getByTestId('empty-executions')).toBeInTheDocument();

    const dismissBtn = screen.getByRole('button', { name: /Dismiss dialog/i });
    fireEvent.click(dismissBtn);
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });

  it('renders initial executions and structured aggregation cards if provided', () => {
    const customExecutions: SummonSessionExecutionData[] = [
      {
        summon_id: 'summon-init-001',
        chat_id: 'test-chat-02',
        specialist_id: 'specialist_code_audit',
        status: 'completed',
        trigger_source: 'explicit_mention',
        instruction: '审查数据库访问权限',
        aggregation_card: {
          card_id: 'card-init-001',
          summon_id: 'summon-init-001',
          specialist_id: 'specialist_code_audit',
          specialist_name: '代码与安全审计专家',
          card_type: 'code_audit',
          headline: '【代码与安全审计专家】产出安全审计报告',
          deliverable_payload: '权限校验通过，无SQL注入风险。',
          artifacts: ['audit_report.json'],
          created_at: 1000,
        },
        execution_seconds: 0.6,
      },
    ];

    render(
      <ConversationalSpecialistSummoningCard
        chatId="test-chat-02"
        initialExecutions={customExecutions}
      />
    );

    expect(screen.getByTestId('stat-summoned-count')).toHaveTextContent('1');
    expect(screen.getByTestId('stat-bridged-cards')).toHaveTextContent('1');
    expect(screen.getByTestId('execution-item-summon-init-001')).toBeInTheDocument();
    expect(screen.getByText(/产出安全审计报告/i)).toBeInTheDocument();
    expect(screen.getByText(/audit_report.json/i)).toBeInTheDocument();
  });

  it('triggers quick @-mention from specialist roster button and enables summon', () => {
    render(<ConversationalSpecialistSummoningCard chatId="test-chat-03" />);

    const quickBtn = screen.getByTestId('btn-quick-mention-specialist_humanize');
    fireEvent.click(quickBtn);

    const input = screen.getByTestId('input-summon-text') as HTMLInputElement;
    expect(input.value).toContain('@去AI味专家');

    expect(screen.getByTestId('detected-banner')).toBeInTheDocument();
    expect(screen.getByText(/Explicit @-Tag/i)).toBeInTheDocument();
    expect(screen.getByTestId('btn-dispatch-summon')).not.toBeDisabled();
  });

  it('detects implicit keyword intent and performs sandbox summon with structured return card', () => {
    render(<ConversationalSpecialistSummoningCard chatId="test-chat-04" />);

    const input = screen.getByTestId('input-summon-text');
    // Type text matching visual specialist keywords
    fireEvent.change(input, { target: { value: '请为本次新功能发布制作配套的海报与视觉设计配图' } });

    expect(screen.getByTestId('detected-banner')).toBeInTheDocument();
    expect(within(screen.getByTestId('detected-banner')).getByText(/视觉与配图设计专家/i)).toBeInTheDocument();
    expect(screen.getByText(/Implicit Intent/i)).toBeInTheDocument();

    // Dispatch summon
    fireEvent.click(screen.getByTestId('btn-dispatch-summon'));

    expect(screen.getByTestId('stat-summoned-count')).toHaveTextContent('1');
    expect(screen.getByTestId('stat-bridged-cards')).toHaveTextContent('1');
    expect(screen.getByTestId('status-message')).toHaveTextContent(
      "Specialist '视觉与配图设计专家' summoned via intent_detection."
    );
    expect(screen.queryByTestId('empty-executions')).not.toBeInTheDocument();
  });

  it('clears executions and resets summoning state upon clicking reset button', () => {
    render(<ConversationalSpecialistSummoningCard chatId="test-chat-05" />);

    // Quick mention and summon
    fireEvent.click(screen.getByTestId('btn-quick-mention-specialist_market_research'));
    fireEvent.click(screen.getByTestId('btn-dispatch-summon'));

    expect(screen.getByTestId('stat-summoned-count')).toHaveTextContent('1');

    // Click reset
    fireEvent.click(screen.getByTestId('btn-reset'));

    expect(screen.getByTestId('stat-summoned-count')).toHaveTextContent('0');
    expect(screen.getByTestId('stat-bridged-cards')).toHaveTextContent('0');
    expect(screen.getByTestId('empty-executions')).toBeInTheDocument();
    expect(screen.getByTestId('status-message')).toHaveTextContent(
      'Specialist summoning state reset.'
    );
  });
});
