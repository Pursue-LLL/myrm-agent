/** @vitest-environment jsdom */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { DeliberationThreadBubble } from '../DeliberationThreadBubble';
import type { DeliberationMessage } from '../groupChatTypes';

const speakingMessage: DeliberationMessage = {
  id: 'msg-speak-01',
  agentId: 'agent-arch',
  agentName: '架构总监',
  role: 'Architect',
  content: '建议采用事件驱动架构与读写分离模式，保证高吞吐。',
  status: 'speaking',
  timestamp: '14:20:05',
  colorBadge: '#6366f1',
  options: ['采纳方案 A: CQRS 读写分离', '采纳方案 B: 传统单库加缓存'],
};

const passMessage: DeliberationMessage = {
  id: 'msg-pass-02',
  agentId: 'agent-qa',
  agentName: '安全审计官',
  role: 'Security',
  content: '本次改动未引入外部三方依赖与未鉴权端口，安全合规，无需拦截。',
  status: 'pass',
  passReason: '代码变更仅包含内部类型重构，无敏感 API 暴露风险。',
  timestamp: '14:20:10',
  colorBadge: '#f59e0b',
};

const needsYouMessage: DeliberationMessage = {
  id: 'msg-ny-03',
  agentId: 'agent-coder',
  agentName: '全栈执行官',
  role: 'Coder',
  content: '数据库迁移在生产环境有轻微锁表风险，请求人类负责人授权。',
  status: 'needs-you',
  timestamp: '14:20:15',
  colorBadge: '#10b981',
};

describe('DeliberationThreadBubble Component', () => {
  it('renders active speaking message with role badge, content and options', () => {
    const onSelectOptionMock = vi.fn();

    render(
      <DeliberationThreadBubble
        message={speakingMessage}
        onSelectOption={onSelectOptionMock}
      />,
    );

    expect(screen.getByTestId('deliberation-bubble-msg-speak-01')).toBeDefined();
    expect(screen.getByText('架构总监')).toBeDefined();
    expect(screen.getByText('Architect')).toBeDefined();
    expect(screen.getByText('建议采用事件驱动架构与读写分离模式，保证高吞吐。')).toBeDefined();

    // Option chips
    const chipA = screen.getByRole('button', { name: /采纳方案 A/i });
    fireEvent.click(chipA);
    expect(onSelectOptionMock).toHaveBeenCalledWith('采纳方案 A: CQRS 读写分离');
  });

  it('collapses silent PASS message by default and expands reasoning on click', () => {
    render(<DeliberationThreadBubble message={passMessage} />);

    expect(screen.getByTestId('deliberation-pass-msg-pass-02')).toBeDefined();
    expect(screen.getByText(/PASS|passBadge|静默/i)).toBeDefined();

    // Details not visible initially
    expect(screen.queryByTestId('deliberation-pass-details-msg-pass-02')).toBeNull();

    // Click to expand reasoning
    const toggleBtn = screen.getByRole('button');
    fireEvent.click(toggleBtn);

    expect(screen.getByTestId('deliberation-pass-details-msg-pass-02')).toBeDefined();
    expect(screen.getByText('代码变更仅包含内部类型重构，无敏感 API 暴露风险。')).toBeDefined();

    // Click again to collapse
    fireEvent.click(toggleBtn);
    expect(screen.queryByTestId('deliberation-pass-details-msg-pass-02')).toBeNull();
  });

  it('renders needs-you highlight alert for escalated turns', () => {
    render(<DeliberationThreadBubble message={needsYouMessage} />);

    expect(screen.getByText(/Needs You|人类协同裁决/i)).toBeDefined();
    expect(screen.getByText('数据库迁移在生产环境有轻微锁表风险，请求人类负责人授权。')).toBeDefined();
  });
});
