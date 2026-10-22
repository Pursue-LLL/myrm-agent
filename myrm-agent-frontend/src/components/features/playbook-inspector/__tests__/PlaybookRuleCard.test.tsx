import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PlaybookRuleCard } from '../PlaybookRuleCard';
import type { PlaybookRule } from '../playbookInspectorTypes';

describe('PlaybookRuleCard', () => {
  const mockRule: PlaybookRule = {
    id: 'test-rule-1',
    title: '单文件行数治理',
    triggerCondition: '文件修改时',
    directive: '严格控制在 400 行以内',
    status: 'degraded',
    triggerCount: 30,
    successCount: 18,
    winRate: 0.6,
    isPinned: false,
    recentFailures: [
      {
        sessionId: 'sess-fail-1',
        timestamp: Date.now(),
        errorSummary: '文件生成超标达到 450 行',
        contextSnippet: 'class OvergrownModule { ... }',
      },
    ],
    lastTriggeredAt: Date.now(),
    updatedAt: Date.now(),
  };

  it('renders status badge and title correctly', () => {
    render(
      <PlaybookRuleCard
        rule={mockRule}
        onRevive={vi.fn()}
        onTogglePin={vi.fn()}
        onRetire={vi.fn()}
        onEdit={vi.fn()}
      />
    );
    expect(screen.getByText('降权观察')).toBeDefined();
    expect(screen.getByText('单文件行数治理')).toBeDefined();
    expect(screen.getByText('严格控制在 400 行以内')).toBeDefined();
  });

  it('renders win rate percentage and trigger count', () => {
    render(
      <PlaybookRuleCard
        rule={mockRule}
        onRevive={vi.fn()}
        onTogglePin={vi.fn()}
        onRetire={vi.fn()}
        onEdit={vi.fn()}
      />
    );
    expect(screen.getByText(/胜率 60%/)).toBeDefined();
    expect(screen.getByText(/触发 30 次/)).toBeDefined();
  });

  it('calls onRevive when clicking revive button', () => {
    const onRevive = vi.fn();
    render(
      <PlaybookRuleCard
        rule={mockRule}
        onRevive={onRevive}
        onTogglePin={vi.fn()}
        onRetire={vi.fn()}
        onEdit={vi.fn()}
      />
    );
    const reviveBtn = screen.getByRole('button', { name: /一键强制复活规约/ });
    fireEvent.click(reviveBtn);
    expect(onRevive).toHaveBeenCalledTimes(1);
  });

  it('toggles recent failures expandable view', () => {
    render(
      <PlaybookRuleCard
        rule={mockRule}
        onRevive={vi.fn()}
        onTogglePin={vi.fn()}
        onRetire={vi.fn()}
        onEdit={vi.fn()}
      />
    );
    const toggleFailuresBtn = screen.getByRole('button', { name: /最近失败会话追溯/ });
    fireEvent.click(toggleFailuresBtn);

    expect(screen.getByText('文件生成超标达到 450 行')).toBeDefined();
    expect(screen.getByText('class OvergrownModule { ... }')).toBeDefined();
  });
});
