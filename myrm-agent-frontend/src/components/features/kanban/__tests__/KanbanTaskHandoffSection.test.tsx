import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { KanbanTask } from '@/services/kanban';
import { KanbanTaskHandoffSection } from '../KanbanTaskHandoffSection';

const mockMoveTask = vi.fn();
vi.mock('@/services/kanban', () => ({
  moveTask: (...args: unknown[]) => mockMoveTask(...args),
}));

vi.mock('@/store/useAgentStore', () => ({
  default: (selector: (state: { agents: Array<{ id: string; name: string }> }) => unknown) =>
    selector({
      agents: [
        { id: 'agent-dev', name: 'Developer Agent' },
        { id: 'agent-arch', name: 'Architect Agent' },
        { id: 'agent-qa', name: 'QA Engineer' },
      ],
    }),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

const mockT = (key: string): string => {
  const translations: Record<string, string> = {
    taskHandoff: '任务移交协作 (Handoff)',
    delegateTask: '+ 移交给新成员',
    collapse: '收起',
    currentAssignee: '当前经办',
    unassigned: '未指派数字员工',
    transferToAgent: '移交给成员 (数字员工)',
    selectAgentPlaceholder: '-- 选择目标数字员工 --',
    targetStatus: '移交后状态',
    handoffSummary: '移交说明 / 前因后果',
    changedFilesMetadata: '涉及/产出文件列表 (多文件以换行或逗号分隔)',
    confirmHandoff: '确认移交',
    handoffHistory: '移交流转履历',
    changedFiles: '变更文件',
  };
  return translations[key] || key;
};

const makeTask = (overrides?: Partial<KanbanTask>): KanbanTask => ({
  task_id: 'task-101',
  board_id: 'board-alpha',
  title: 'Implement OAuth Token Revocation',
  description: 'Revoke tokens on logout',
  status: 'backlog',
  priority: 'normal',
  agent_id: 'agent-dev',
  model_override: null,
  parent_task_id: null,
  workspace_path: null,
  branch: null,
  goal_mode: false,
  goal_max_turns: null,
  require_approval: false,
  max_runtime_seconds: null,
  extra_skill_ids: [],
  retry_count: 0,
  max_retries: 3,
  consecutive_failures: 0,
  progress_note: null,
  blocked_reason: null,
  block_kind: null,
  scheduled_until: null,
  result: '',
  error: '',
  attachment_ids: [],
  attachments: [],
  dep_count: 0,
  children_total: 0,
  children_done: 0,
  comment_count: 0,
  metadata: {
    handoff_history: [
      {
        from_agent_id: 'agent-arch',
        to_agent_id: 'agent-dev',
        summary: 'Architecture specification complete, delegated to dev.',
        changed_files: ['src/auth/service.py', 'src/auth/jwt.py'],
        timestamp: '2026-10-12T10:00:00Z',
      },
    ],
  },
  created_at: '2026-10-12T09:00:00Z',
  updated_at: '2026-10-12T10:00:00Z',
  ...overrides,
});

describe('KanbanTaskHandoffSection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders current assignee and historical handoff timeline', () => {
    const task = makeTask();
    const onChanged = vi.fn();

    render(<KanbanTaskHandoffSection task={task} onChanged={onChanged} t={mockT} />);

    // Shows current assignee name (appears in assignee badge and history)
    expect(screen.getAllByText('Developer Agent').length).toBeGreaterThanOrEqual(1);
    // Shows history timeline entry
    expect(screen.getByText('Architect Agent')).toBeDefined();
    expect(screen.getByText('Architecture specification complete, delegated to dev.')).toBeDefined();
    expect(screen.getByText('src/auth/service.py')).toBeDefined();
    expect(screen.getByText('src/auth/jwt.py')).toBeDefined();
  });

  it('toggles handoff delegation form and allows submitting a task transfer', async () => {
    const task = makeTask();
    const onChanged = vi.fn();
    mockMoveTask.mockResolvedValueOnce({ success: true });

    render(<KanbanTaskHandoffSection task={task} onChanged={onChanged} t={mockT} />);

    // Expand delegation form
    const toggleButton = screen.getByText('+ 移交给新成员');
    fireEvent.click(toggleButton);

    expect(screen.getByText('收起')).toBeDefined();

    // Select target agent (first combobox is agent selector)
    const selects = screen.getAllByRole('combobox');
    fireEvent.change(selects[0], { target: { value: 'agent-qa' } });

    // Fill in summary and files
    const textareas = screen.getAllByRole('textbox');
    expect(textareas.length).toBe(2);
    fireEvent.change(textareas[0], { target: { value: 'Feature implemented, ready for QA' } });
    fireEvent.change(textareas[1], { target: { value: 'src/auth/service.py\ntests/auth_test.py' } });

    // Submit handoff
    const submitBtn = screen.getByText('确认移交');
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockMoveTask).toHaveBeenCalledWith(
        'task-101',
        'ready',
        expect.objectContaining({
          assignee_agent_id: 'agent-qa',
          result: 'Feature implemented, ready for QA',
          metadata: {
            changed_files: ['src/auth/service.py', 'tests/auth_test.py'],
            note: 'Feature implemented, ready for QA',
          },
        })
      );
      expect(onChanged).toHaveBeenCalled();
    });
  });
});
