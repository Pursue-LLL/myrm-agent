import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { AsyncAgentMessageCard } from '../AsyncAgentMessageCard';

const mockDict: Record<string, string> = {
  progressReport: '实时进度通报',
  milestone: '阶段性成果',
  decisionInquiry: '非阻塞决策征询',
  confirmedDecision: '已确认决策：',
  resolvedBadge: '已解决',
  recommendedPlan: '推荐采纳预案',
  adopt: '采纳',
  customReply: '自定义回复',
  collapseCustom: '收起自定义',
  inputPlaceholder: '输入指导或补充说明...',
  send: '发送',
};

const stableT = (key: string) => mockDict[key] ?? key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('AsyncAgentMessageCard', () => {
  it('renders progress notification with correct title, message and data-call-id without leaking raw ID in UI', () => {
    const { container } = render(
      <AsyncAgentMessageCard callId="async_msg_123456" message="Scanning files..." category="progress" />,
    );

    expect(screen.getByText('实时进度通报')).toBeDefined();
    expect(screen.getByText('Scanning files...')).toBeDefined();
    expect(container.querySelector('[data-call-id="async_msg_123456"]')).not.toBeNull();
    expect(screen.queryByText(/ID:/i)).toBeNull();
  });

  it('renders milestone notification', () => {
    render(<AsyncAgentMessageCard callId="async_msg_789abc" message="Build finished in 45s" category="milestone" />);

    expect(screen.getByText('阶段性成果')).toBeDefined();
    expect(screen.getByText('Build finished in 45s')).toBeDefined();
  });

  it('handles adopting recommendation on question category', async () => {
    const handleSteer = vi.fn().mockResolvedValue(undefined);
    render(
      <AsyncAgentMessageCard
        callId="async_msg_question1"
        message="Remove deprecated routes?"
        category="question"
        recommendation="Keep legacy compatibility"
        onSteerReply={handleSteer}
      />,
    );

    expect(screen.getByText('非阻塞决策征询')).toBeDefined();
    expect(screen.getByText('Keep legacy compatibility')).toBeDefined();

    const adoptBtn = screen.getByText('采纳');
    fireEvent.click(adoptBtn);

    expect(handleSteer).toHaveBeenCalledWith(
      'Keep legacy compatibility',
      'async_msg_question1',
      'Remove deprecated routes?',
    );

    // Wait for async state update to collapse to resolved status
    await waitFor(() => {
      expect(screen.getByText('已确认决策：')).toBeDefined();
    });
  });

  it('handles clicking suggestedReplies chips to trigger steering reply', async () => {
    const handleSteer = vi.fn().mockResolvedValue(undefined);
    render(
      <AsyncAgentMessageCard
        callId="async_msg_question2"
        message="Which database migration strategy should we use?"
        category="question"
        suggestedReplies={['Blue-Green', 'Canary', 'In-Place']}
        onSteerReply={handleSteer}
      />,
    );

    expect(screen.getByText('Blue-Green')).toBeDefined();
    expect(screen.getByText('Canary')).toBeDefined();
    expect(screen.getByText('In-Place')).toBeDefined();

    const canaryBtn = screen.getByText('Canary');
    fireEvent.click(canaryBtn);

    expect(handleSteer).toHaveBeenCalledWith(
      'Canary',
      'async_msg_question2',
      'Which database migration strategy should we use?',
    );

    await waitFor(() => {
      expect(screen.getByText('已确认决策：')).toBeDefined();
      expect(screen.getByText('Canary')).toBeDefined();
    });
  });

  it('handles custom reply on question without recommendation', async () => {
    const handleSteer = vi.fn().mockResolvedValue(undefined);
    render(
      <AsyncAgentMessageCard
        callId="async_msg_question3"
        message="Need more context on target deployment."
        category="question"
        onSteerReply={handleSteer}
      />,
    );

    const toggleBtn = screen.getByText('自定义回复');
    fireEvent.click(toggleBtn);

    const input = screen.getByPlaceholderText('输入指导或补充说明...');
    fireEvent.change(input, { target: { value: 'Deploy to staging first' } });

    const submitBtn = screen.getByRole('button', { name: /发送/i });
    fireEvent.click(submitBtn);

    expect(handleSteer).toHaveBeenCalledWith(
      'Deploy to staging first',
      'async_msg_question3',
      'Need more context on target deployment.',
    );

    await waitFor(() => {
      expect(screen.getByText('已确认决策：')).toBeDefined();
      expect(screen.getByText('Deploy to staging first')).toBeDefined();
    });
  });
});
