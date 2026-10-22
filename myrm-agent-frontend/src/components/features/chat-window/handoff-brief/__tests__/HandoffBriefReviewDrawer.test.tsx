import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { HandoffBriefReviewDrawer } from '../HandoffBriefReviewDrawer';
import { useHandoffBriefStore } from '../useHandoffBriefStore';
import type { HandoffBrief } from '../handoffBriefTypes';

describe('HandoffBriefReviewDrawer', () => {
  beforeEach(() => {
    useHandoffBriefStore.getState().reset();
    vi.restoreAllMocks();
  });

  const mockBrief: HandoffBrief = {
    sessionId: 'sess-888',
    sessionTitle: '数据库分库分表迁移',
    summary: '完成 ShardingSphere 读写分离配置，待实测高并发连接池。',
    precomputedAt: Date.now(),
    precomputeDurationMs: 18,
    artifacts: ['config/sharding.yaml'],
    items: [
      {
        id: 'item-d1',
        category: 'decision',
        content: '主键采用 Snowflake 雪花算法',
        enabled: true,
      },
      {
        id: 'item-t1',
        category: 'todo',
        content: '压测 HikariCP 连接池最大活跃数',
        enabled: true,
      },
      {
        id: 'item-c1',
        category: 'constraint',
        content: '严禁跨库分布式事务，采用最终一致性',
        enabled: true,
      },
    ],
  };

  it('renders nothing when drawer is closed or brief not found', () => {
    const { container } = render(
      <HandoffBriefReviewDrawer sessionId="sess-unknown" />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders header, duration badge and items when drawer is opened', () => {
    useHandoffBriefStore.getState().setBrief(mockBrief);
    useHandoffBriefStore.getState().openDrawer('sess-888');

    render(<HandoffBriefReviewDrawer sessionId="sess-888" />);

    expect(screen.getByText('跨会话交接简报审阅')).toBeDefined();
    expect(screen.getByText('18ms 预就绪')).toBeDefined();
    expect(screen.getByText(/完成 ShardingSphere 读写分离配置/)).toBeDefined();
    expect(screen.getByText('主键采用 Snowflake 雪花算法')).toBeDefined();
    expect(screen.getByText('压测 HikariCP 连接池最大活跃数')).toBeDefined();
  });

  it('filters items when clicking category filter buttons', () => {
    useHandoffBriefStore.getState().setBrief(mockBrief);
    useHandoffBriefStore.getState().openDrawer('sess-888');

    render(<HandoffBriefReviewDrawer sessionId="sess-888" />);

    const todoFilterBtn = screen.getByRole('button', { name: '待办' });
    fireEvent.click(todoFilterBtn);

    expect(screen.queryByText('主键采用 Snowflake 雪花算法')).toBeNull();
    expect(screen.getByText('压测 HikariCP 连接池最大活跃数')).toBeDefined();
  });

  it('adds custom supplementary item to list', () => {
    useHandoffBriefStore.getState().setBrief(mockBrief);
    useHandoffBriefStore.getState().openDrawer('sess-888');

    render(<HandoffBriefReviewDrawer sessionId="sess-888" />);

    const input = screen.getByRole('textbox', { name: /补充条目内容/ });
    fireEvent.change(input, { target: { value: '新增约束：表名必须带年份后缀' } });

    const addBtn = screen.getByRole('button', { name: /添加/ });
    fireEvent.click(addBtn);

    expect(screen.getByText('新增约束：表名必须带年份后缀')).toBeDefined();
  });

  it('triggers onConfirmInject with constructed payload', () => {
    const onConfirmInject = vi.fn();
    useHandoffBriefStore.getState().setBrief(mockBrief);
    useHandoffBriefStore.getState().openDrawer('sess-888');

    render(<HandoffBriefReviewDrawer sessionId="sess-888" onConfirmInject={onConfirmInject} />);

    const confirmBtn = screen.getByRole('button', { name: /确认注入新会话/ });
    fireEvent.click(confirmBtn);

    expect(onConfirmInject).toHaveBeenCalledTimes(1);
    const [payload] = onConfirmInject.mock.calls[0];
    expect(payload.sourceSessionId).toBe('sess-888');
    expect(payload.injectedPrompt).toContain('【核心架构决策】');
    expect(payload.injectedPrompt).toContain('主键采用 Snowflake 雪花算法');
  });
});
