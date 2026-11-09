'use client';

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { MemoryRecallBoundaryData } from '@/services/memory/commandCenter';

import { MemoryRecallBoundaryPanel } from '../command-center/MemoryRecallBoundaryPanel';

const intl = vi.hoisted(() => ({ locale: 'zh' as 'en' | 'zh' }));

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => intl.locale));

const { mockGetMemoryRecallBoundary } = vi.hoisted(() => ({ mockGetMemoryRecallBoundary: vi.fn() }));

vi.mock('@/services/memory/commandCenter', () => ({ getMemoryRecallBoundary: mockGetMemoryRecallBoundary }));

const boundary: MemoryRecallBoundaryData = {
  agent_id: null,
  task_id: null,
  read_scopes: [
    {
      level: 'global',
      label: 'Global Shared Knowledge',
      is_active: true,
      namespace_pattern: 'global',
      description: 'System-wide persistent facts and rules',
    },
    {
      level: 'task',
      label: 'Task Boundary (active)',
      is_active: false,
      namespace_pattern: 'task:active',
      description: 'Ephemeral execution session memory',
    },
  ],
  write_policy: 'inherit',
  partitions: {
    identity_count: 1,
    session_memory_count: 8,
    operating_instructions_count: 2,
    retrievable_evidence_count: 48,
  },
  candidate_records: [],
  approved_records: [
    {
      id: 'sem-1',
      memory_type: 'semantic',
      content_preview: 'likes tea',
      namespace: 'agent:a1',
      partition: 'retrievable_evidence',
      importance: 0.8,
      access_count: 3,
      is_pinned: true,
    },
    {
      id: 'rule-1',
      memory_type: 'procedural',
      content_preview: 'ask before changing the schema',
      namespace: 'global',
      partition: 'operating_instructions',
      importance: null,
      access_count: 1,
      is_pinned: false,
    },
  ],
  total_candidates: 0,
  total_approved: 59,
};

const openTab = async (name: RegExp) => fireEvent.click(await screen.findByRole('tab', { name }));

describe('MemoryRecallBoundaryPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    intl.locale = 'zh';
    mockGetMemoryRecallBoundary.mockResolvedValue(boundary);
  });

  it('asks for the boundary of the given agent and task', async () => {
    render(<MemoryRecallBoundaryPanel agentId="a1" taskId="t1" />);

    await screen.findByRole('tab', { name: /已生效参与召回记忆/ });
    expect(mockGetMemoryRecallBoundary).toHaveBeenCalledWith('a1', 't1');
  });

  it('shows the stored count of each partition, without any character budget', async () => {
    const { container } = render(<MemoryRecallBoundaryPanel />);

    await openTab(/四记忆职责分区/);

    expect(screen.getByText('1 条')).toBeDefined();
    expect(screen.getByText('8 条')).toBeDefined();
    expect(screen.getByText('2 条')).toBeDefined();
    expect(screen.getByText('48 条')).toBeDefined();
    expect(screen.getByText('事实知识、过往经历与已验证的结论。')).toBeDefined();
    expect(container.textContent).not.toMatch(/预算|字符|6000/);
  });

  it('pluralises the partition count in English', async () => {
    intl.locale = 'en';
    render(<MemoryRecallBoundaryPanel />);

    await openTab(/Four Memory Partitions/);

    expect(screen.getByText('1 memory')).toBeDefined();
    expect(screen.getByText('48 memories')).toBeDefined();
  });

  it('lists a sample of the approved memories and says it is a sample', async () => {
    render(<MemoryRecallBoundaryPanel />);

    await openTab(/已生效参与召回记忆.*\(59\)/);

    expect(screen.getByText('已生效记忆共 59 条，此处显示其中 2 条。')).toBeDefined();
    // Types and partitions read as product wording, not as stored identifiers.
    expect(screen.getByText('知识')).toBeDefined();
    expect(screen.getByText('事实证据')).toBeDefined();
    expect(screen.getByText('方法')).toBeDefined();
    expect(screen.getByText('操作准则')).toBeDefined();
    expect(screen.getByText('范围：agent:a1')).toBeDefined();
    expect(screen.getByText('置顶')).toBeDefined();
  });

  it('shows the importance only for a memory that has one', async () => {
    render(<MemoryRecallBoundaryPanel />);

    await openTab(/已生效参与召回记忆/);

    expect(screen.getByText('重要度 0.80 · 已召回 3 次')).toBeDefined();
    expect(screen.getByText('已召回 1 次')).toBeDefined();
    expect(screen.getAllByText(/重要度/)).toHaveLength(1);
  });

  it('does not claim a sample when every approved memory is listed', async () => {
    mockGetMemoryRecallBoundary.mockResolvedValue({ ...boundary, total_approved: 2 });
    render(<MemoryRecallBoundaryPanel />);

    await openTab(/已生效参与召回记忆/);

    expect(screen.queryByText(/此处显示其中/)).toBeNull();
  });

  it('opens on the candidate pool and says when it is empty', async () => {
    render(<MemoryRecallBoundaryPanel />);

    expect(await screen.findByText('当前候选待审池为空，记忆处于清爽健康状态')).toBeDefined();
  });

  it('lists each pending candidate with its type, confidence and source', async () => {
    mockGetMemoryRecallBoundary.mockResolvedValue({
      ...boundary,
      candidate_records: [
        {
          id: 'cand-1',
          memory_type: 'episodic',
          content_preview: 'moved to Berlin last spring',
          confidence: 0.857,
          source: 'conversation',
          created_at: '2026-11-01T08:00:00Z',
          status: 'review_required',
        },
      ],
      total_candidates: 1,
    });
    render(<MemoryRecallBoundaryPanel />);

    expect(await screen.findByText('moved to Berlin last spring')).toBeDefined();
    expect(screen.getByText('经历')).toBeDefined();
    expect(screen.getByText('置信度: 86%')).toBeDefined();
    expect(screen.getByText('来源: conversation')).toBeDefined();
    expect(screen.queryByText('当前候选待审池为空，记忆处于清爽健康状态')).toBeNull();
  });

  it('says when there is no approved memory', async () => {
    mockGetMemoryRecallBoundary.mockResolvedValue({ ...boundary, approved_records: [], total_approved: 0 });
    render(<MemoryRecallBoundaryPanel />);

    await openTab(/已生效参与召回记忆/);

    expect(screen.getByText('暂无已生效记忆')).toBeDefined();
  });

  it('keeps the data and disables refresh while the boundary reloads', async () => {
    render(<MemoryRecallBoundaryPanel />);
    await screen.findByRole('tab', { name: /已生效参与召回记忆/ });

    let finishReload: (data: MemoryRecallBoundaryData) => void = () => undefined;
    mockGetMemoryRecallBoundary.mockReturnValueOnce(
      new Promise<MemoryRecallBoundaryData>((resolve) => {
        finishReload = resolve;
      }),
    );
    const refresh = screen.getByRole('button', { name: '刷新边界' }) as HTMLButtonElement;
    fireEvent.click(refresh);

    await waitFor(() => expect(refresh.disabled).toBe(true));
    expect(screen.getByRole('tab', { name: /已生效参与召回记忆/ })).toBeDefined();

    finishReload(boundary);
    await waitFor(() => expect(refresh.disabled).toBe(false));
  });

  it('marks which read scopes are active', async () => {
    render(<MemoryRecallBoundaryPanel />);

    await openTab(/任务召回边界/);

    expect(screen.getByText('生效中')).toBeDefined();
    expect(screen.getByText('受限')).toBeDefined();
  });

  it('reports a failed load in plain words and recovers on refresh', async () => {
    mockGetMemoryRecallBoundary.mockRejectedValueOnce(new Error('HTTP 500 upstream exploded'));
    render(<MemoryRecallBoundaryPanel />);

    await screen.findByText('召回边界加载失败，请重试。');
    expect(screen.queryByText(/upstream exploded/)).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: '刷新边界' }));

    await waitFor(() => expect(screen.getByRole('tab', { name: /已生效参与召回记忆/ })).toBeDefined());
    expect(mockGetMemoryRecallBoundary).toHaveBeenCalledTimes(2);
  });
});
