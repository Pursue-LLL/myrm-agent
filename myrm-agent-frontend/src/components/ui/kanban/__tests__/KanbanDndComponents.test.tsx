import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { KanbanDropColumn } from '../KanbanDndComponents';
import type { KanbanTask, TaskStatus } from '@/services/kanban';

vi.mock('@dnd-kit/core', () => ({
  useDroppable: vi.fn(() => ({ setNodeRef: vi.fn(), isOver: false })),
  useDraggable: vi.fn(() => ({
    attributes: { role: 'button', tabIndex: 0, 'aria-roledescription': 'draggable' },
    listeners: {},
    setNodeRef: vi.fn(),
    isDragging: false,
  })),
}));

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('../KanbanTaskCard', () => ({
  default: ({ task }: { task: KanbanTask }) => <div data-testid={`task-card-${task.task_id}`}>{task.title}</div>,
}));

function makeMockTask(overrides: Partial<KanbanTask> = {}): KanbanTask {
  return {
    task_id: 'task-1',
    board_id: 'board-1',
    title: 'Test Task',
    description: '',
    status: 'ready' as TaskStatus,
    priority: 'normal',
    retry_count: 0,
    max_retries: 3,
    consecutive_failures: 0,
    result: '',
    error: '',
    metadata: {},
    extra_skill_ids: [],
    attachment_ids: [],
    attachments: [],
    dep_count: 0,
    children_total: 0,
    children_done: 0,
    comment_count: 0,
    created_at: '2026-05-28T00:00:00Z',
    updated_at: '2026-05-28T00:00:00Z',
    ...overrides,
  };
}

describe('KanbanDropColumn', () => {
  const defaultProps = {
    status: 'ready' as TaskStatus,
    tasks: [makeMockTask({ task_id: 'task-1', title: 'Task A' })],
    allTasks: [makeMockTask({ task_id: 'task-1', title: 'Task A' })],
    draggedTaskId: null,
    dragOverColumn: null,
    selectedTaskIds: [] as string[],
    onTaskSelect: vi.fn(),
    onMoveTask: vi.fn(),
    onDeleteTask: vi.fn(),
    onReclaimTask: vi.fn(),
    onRefresh: vi.fn(),
    t: ((key: string) => key) as ReturnType<typeof import('next-intl').useTranslations<'kanban'>>,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('渲染列标题和任务计数', () => {
    render(<KanbanDropColumn {...defaultProps} />);
    expect(screen.getByText('status.ready')).toBeInTheDocument();
    expect(screen.getByText('1')).toBeInTheDocument();
  });

  it('渲染所有任务卡片', () => {
    const tasks = [
      makeMockTask({ task_id: 'task-1', title: 'Task A' }),
      makeMockTask({ task_id: 'task-2', title: 'Task B' }),
    ];
    render(<KanbanDropColumn {...defaultProps} tasks={tasks} allTasks={tasks} />);
    expect(screen.getByTestId('task-card-task-1')).toBeInTheDocument();
    expect(screen.getByTestId('task-card-task-2')).toBeInTheDocument();
  });

  it('拖拽高亮时显示占位符', () => {
    render(<KanbanDropColumn {...defaultProps} draggedTaskId="task-x" dragOverColumn="ready" />);
    expect(screen.getByText('dropHere')).toBeInTheDocument();
  });

  it('未拖拽时不显示占位符', () => {
    render(<KanbanDropColumn {...defaultProps} draggedTaskId={null} dragOverColumn={null} />);
    expect(screen.queryByText('dropHere')).not.toBeInTheDocument();
  });

  it('draggedTaskId 存在但 dragOverColumn 不匹配时不高亮', () => {
    render(<KanbanDropColumn {...defaultProps} draggedTaskId="task-x" dragOverColumn="running" />);
    expect(screen.queryByText('dropHere')).not.toBeInTheDocument();
  });

  it('渲染 footer 内容', () => {
    render(<KanbanDropColumn {...defaultProps} footer={<div data-testid="footer">Footer</div>} />);
    expect(screen.getByTestId('footer')).toBeInTheDocument();
  });

  it('空列时不渲染任何卡片', () => {
    render(<KanbanDropColumn {...defaultProps} tasks={[]} />);
    expect(screen.getByText('0')).toBeInTheDocument();
    expect(screen.queryByTestId('task-card-task-1')).not.toBeInTheDocument();
  });

  it('选中任务时显示选中标记', () => {
    render(<KanbanDropColumn {...defaultProps} selectedTaskIds={['task-1']} />);
    const svg = document.querySelector('svg');
    expect(svg).toBeInTheDocument();
  });

  it('Ctrl+click 触发多选', () => {
    const onTaskSelect = vi.fn();
    render(<KanbanDropColumn {...defaultProps} onTaskSelect={onTaskSelect} />);
    const card = screen.getByTestId('task-card-task-1').parentElement!;
    fireEvent.click(card, { ctrlKey: true });
    expect(onTaskSelect).toHaveBeenCalledWith('task-1', expect.any(Object));
  });

  it('普通 click 不触发多选', () => {
    const onTaskSelect = vi.fn();
    render(<KanbanDropColumn {...defaultProps} onTaskSelect={onTaskSelect} />);
    const card = screen.getByTestId('task-card-task-1').parentElement!;
    fireEvent.click(card);
    expect(onTaskSelect).not.toHaveBeenCalled();
  });

  it('Meta+click 触发多选 (Mac)', () => {
    const onTaskSelect = vi.fn();
    render(<KanbanDropColumn {...defaultProps} onTaskSelect={onTaskSelect} />);
    const card = screen.getByTestId('task-card-task-1').parentElement!;
    fireEvent.click(card, { metaKey: true });
    expect(onTaskSelect).toHaveBeenCalledWith('task-1', expect.any(Object));
  });

  it('Shift+click 触发多选', () => {
    const onTaskSelect = vi.fn();
    render(<KanbanDropColumn {...defaultProps} onTaskSelect={onTaskSelect} />);
    const card = screen.getByTestId('task-card-task-1').parentElement!;
    fireEvent.click(card, { shiftKey: true });
    expect(onTaskSelect).toHaveBeenCalledWith('task-1', expect.any(Object));
  });

  it('isDragging 状态时卡片降低透明度', async () => {
    const { useDraggable } = await import('@dnd-kit/core');
    vi.mocked(useDraggable).mockReturnValue({
      attributes: { role: 'button', tabIndex: 0, 'aria-roledescription': 'draggable' } as never,
      listeners: {} as never,
      setNodeRef: vi.fn(),
      isDragging: true,
      node: { current: null } as never,
      activatorEvent: null,
      active: null,
      over: null,
      transform: null,
      rect: { current: null } as never,
    } as never);
    render(<KanbanDropColumn {...defaultProps} />);
    const card = screen.getByTestId('task-card-task-1').parentElement!;
    expect(card.className).toContain('opacity-40');
    expect(card.className).toContain('scale-95');
  });

  describe('Agent 泳道分组 (laneByProfile)', () => {
    const runningTasks = [
      makeMockTask({ task_id: 't1', title: 'Task 1', status: 'running', agent_id: 'agent-a' }),
      makeMockTask({ task_id: 't2', title: 'Task 2', status: 'running', agent_id: 'agent-a' }),
      makeMockTask({ task_id: 't3', title: 'Task 3', status: 'running', agent_id: 'agent-b' }),
      makeMockTask({ task_id: 't4', title: 'Task 4', status: 'running', agent_id: undefined }),
    ];

    const laneProps = {
      ...defaultProps,
      status: 'running' as TaskStatus,
      tasks: runningTasks,
      allTasks: runningTasks,
      laneByProfile: true,
      agentNameMap: new Map([
        ['agent-a', 'Agent Alpha'],
        ['agent-b', 'Agent Beta'],
      ]),
      collapsedAgents: new Set<string>(),
      onToggleAgentCollapse: vi.fn(),
    };

    it('running 列多 agent 时显示泳道 header', () => {
      render(<KanbanDropColumn {...laneProps} />);
      expect(screen.getByText('Agent Alpha')).toBeInTheDocument();
      expect(screen.getByText('Agent Beta')).toBeInTheDocument();
      expect(screen.getByText('unassigned')).toBeInTheDocument();
    });

    it('泳道 header 显示任务计数', () => {
      render(<KanbanDropColumn {...laneProps} />);
      const countLabels = screen.getAllByText('tasksInLane');
      expect(countLabels).toHaveLength(3);
    });

    it('非 running 列不显示泳道', () => {
      render(<KanbanDropColumn {...laneProps} status={'ready' as TaskStatus} />);
      expect(screen.queryByText('Agent Alpha')).not.toBeInTheDocument();
    });

    it('laneByProfile=false 时不显示泳道', () => {
      render(<KanbanDropColumn {...laneProps} laneByProfile={false} />);
      expect(screen.queryByText('Agent Alpha')).not.toBeInTheDocument();
    });

    it('单 agent 时不显示泳道 header（智能隐藏）', () => {
      const singleAgentTasks = [
        makeMockTask({ task_id: 't1', title: 'Task 1', status: 'running', agent_id: 'agent-a' }),
        makeMockTask({ task_id: 't2', title: 'Task 2', status: 'running', agent_id: 'agent-a' }),
      ];
      render(<KanbanDropColumn {...laneProps} tasks={singleAgentTasks} allTasks={singleAgentTasks} />);
      expect(screen.queryByText('Agent Alpha')).not.toBeInTheDocument();
      expect(screen.getByTestId('task-card-t1')).toBeInTheDocument();
      expect(screen.getByTestId('task-card-t2')).toBeInTheDocument();
    });

    it('折叠泳道时隐藏该泳道的任务卡片', () => {
      render(<KanbanDropColumn {...laneProps} collapsedAgents={new Set(['agent-a'])} />);
      expect(screen.getByText('Agent Alpha')).toBeInTheDocument();
      expect(screen.queryByTestId('task-card-t1')).not.toBeInTheDocument();
      expect(screen.queryByTestId('task-card-t2')).not.toBeInTheDocument();
      expect(screen.getByTestId('task-card-t3')).toBeInTheDocument();
      expect(screen.getByTestId('task-card-t4')).toBeInTheDocument();
    });

    it('点击泳道 header 触发折叠回调', () => {
      const onToggle = vi.fn();
      render(<KanbanDropColumn {...laneProps} onToggleAgentCollapse={onToggle} />);
      fireEvent.click(screen.getByText('Agent Alpha'));
      expect(onToggle).toHaveBeenCalledWith('agent-a');
    });

    it('agentNameMap 无映射时 fallback 到原始 ID', () => {
      render(<KanbanDropColumn {...laneProps} agentNameMap={new Map()} />);
      expect(screen.getByText('agent-a')).toBeInTheDocument();
      expect(screen.getByText('agent-b')).toBeInTheDocument();
    });

    it('未分配任务排在已分配之后', () => {
      render(<KanbanDropColumn {...laneProps} />);
      const buttons = screen.getAllByRole('button');
      const laneButtons = buttons.filter((b) => b.className.includes('group/lane'));
      const texts = laneButtons.map((b) => b.textContent);
      const unassignedIdx = texts.findIndex((t) => t?.includes('unassigned'));
      expect(unassignedIdx).toBe(laneButtons.length - 1);
    });

    it('空 running 列 + laneByProfile=true 不渲染泳道', () => {
      render(<KanbanDropColumn {...laneProps} tasks={[]} allTasks={[]} />);
      expect(screen.queryByText('Agent Alpha')).not.toBeInTheDocument();
      expect(screen.getByText('0')).toBeInTheDocument();
    });

    it('所有任务均无 agent_id 时智能隐藏泳道', () => {
      const unassignedOnly = [
        makeMockTask({ task_id: 't1', title: 'U1', status: 'running', agent_id: undefined }),
        makeMockTask({ task_id: 't2', title: 'U2', status: 'running', agent_id: undefined }),
      ];
      render(<KanbanDropColumn {...laneProps} tasks={unassignedOnly} allTasks={unassignedOnly} />);
      expect(screen.queryByText('unassigned')).not.toBeInTheDocument();
      expect(screen.getByTestId('task-card-t1')).toBeInTheDocument();
      expect(screen.getByTestId('task-card-t2')).toBeInTheDocument();
    });

    it('多个泳道全部折叠时所有卡片隐藏', () => {
      render(<KanbanDropColumn {...laneProps} collapsedAgents={new Set(['agent-a', 'agent-b', '__unassigned__'])} />);
      expect(screen.getByText('Agent Alpha')).toBeInTheDocument();
      expect(screen.getByText('Agent Beta')).toBeInTheDocument();
      expect(screen.queryByTestId('task-card-t1')).not.toBeInTheDocument();
      expect(screen.queryByTestId('task-card-t2')).not.toBeInTheDocument();
      expect(screen.queryByTestId('task-card-t3')).not.toBeInTheDocument();
      expect(screen.queryByTestId('task-card-t4')).not.toBeInTheDocument();
    });

    it('泳道按 agent 名称字母排序', () => {
      const sortTasks = [
        makeMockTask({ task_id: 't1', title: 'Z', status: 'running', agent_id: 'agent-z' }),
        makeMockTask({ task_id: 't2', title: 'A', status: 'running', agent_id: 'agent-a' }),
        makeMockTask({ task_id: 't3', title: 'M', status: 'running', agent_id: 'agent-m' }),
      ];
      render(
        <KanbanDropColumn
          {...laneProps}
          tasks={sortTasks}
          allTasks={sortTasks}
          agentNameMap={
            new Map([
              ['agent-z', 'Zeta'],
              ['agent-a', 'Alpha'],
              ['agent-m', 'Mike'],
            ])
          }
        />,
      );
      const buttons = screen.getAllByRole('button');
      const laneButtons = buttons.filter((b) => b.className.includes('group/lane'));
      const names = laneButtons.map((b) => b.textContent?.replace(/tasksInLane/g, '').trim());
      expect(names).toEqual(['Alpha', 'Mike', 'Zeta']);
    });

    it('拖拽高亮与泳道模式共存', () => {
      render(<KanbanDropColumn {...laneProps} draggedTaskId="external-task" dragOverColumn="running" />);
      expect(screen.getByText('dropHere')).toBeInTheDocument();
      expect(screen.getByText('Agent Alpha')).toBeInTheDocument();
    });

    it('collapsedAgents 含不存在的 key 不影响渲染', () => {
      render(<KanbanDropColumn {...laneProps} collapsedAgents={new Set(['nonexistent-agent'])} />);
      expect(screen.getByTestId('task-card-t1')).toBeInTheDocument();
      expect(screen.getByTestId('task-card-t3')).toBeInTheDocument();
    });

    it('agentNameMap 部分映射时混合显示名称和原始 ID', () => {
      render(<KanbanDropColumn {...laneProps} agentNameMap={new Map([['agent-a', 'Alpha']])} />);
      expect(screen.getByText('Alpha')).toBeInTheDocument();
      expect(screen.getByText('agent-b')).toBeInTheDocument();
    });

    it('agent_id 为空字符串时视为 unassigned', () => {
      const emptyIdTasks = [
        makeMockTask({ task_id: 't1', title: 'E1', status: 'running', agent_id: 'agent-a' }),
        makeMockTask({ task_id: 't2', title: 'E2', status: 'running', agent_id: '' as unknown as undefined }),
      ];
      render(
        <KanbanDropColumn
          {...laneProps}
          tasks={emptyIdTasks}
          allTasks={emptyIdTasks}
          agentNameMap={new Map([['agent-a', 'Alpha']])}
        />,
      );
      expect(screen.getByText('Alpha')).toBeInTheDocument();
      expect(screen.getByTestId('task-card-t1')).toBeInTheDocument();
      expect(screen.getByTestId('task-card-t2')).toBeInTheDocument();
    });
  });
});
