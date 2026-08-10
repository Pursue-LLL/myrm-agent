import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { KanbanTask, TaskStatus } from '@/services/kanban';
import { TaskDetailsSection } from '../KanbanTaskDrawerDetails';

const stableT = (key: string) => key;

vi.mock('../KanbanMarkdown', () => ({
  default: ({ children }: { children: string }) => <span>{children}</span>,
}));

vi.mock('@/services/kanban', () => ({
  KANBAN_SOURCE_CHAT_METADATA_KEY: 'source_chat_id',
  hasKanbanCompletionIntent: () => false,
}));

function makeTask(overrides: Partial<KanbanTask> = {}): KanbanTask {
  return {
    task_id: 'task-detail-1',
    board_id: 'board-1',
    title: 'Detail Task',
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
    created_at: '2026-05-29T00:00:00Z',
    updated_at: '2026-05-29T00:00:00Z',
    ...overrides,
  };
}

function renderSection(task: KanbanTask, onRequireApprovalChange = vi.fn()) {
  return render(
    <TaskDetailsSection
      task={task}
      agentName={null}
      progressPill={null}
      editingTimeout={false}
      setEditingTimeout={() => {}}
      timeoutValue={null}
      setTimeoutValue={() => {}}
      handleSaveTimeout={() => {}}
      editingSkills={false}
      setEditingSkills={() => {}}
      skillsText=""
      setSkillsText={() => {}}
      handleSaveSkills={() => {}}
      editingCriteria={false}
      setEditingCriteria={() => {}}
      criteriaText=""
      setCriteriaText={() => {}}
      savingCriteria={false}
      handleSaveCriteria={() => {}}
      assignedAgent={null}
      agents={[]}
      handleAgentChange={() => {}}
      enabledModels={[]}
      editingModel={false}
      setEditingModel={() => {}}
      modelValue=""
      setModelValue={() => {}}
      handleSaveModel={() => {}}
      handleRequireApprovalChange={onRequireApprovalChange}
      t={stableT}
    />,
  );
}

describe('TaskDetailsSection approval gate', () => {
  it('renders an editable checkbox for active statuses', () => {
    renderSection(makeTask({ status: 'ready' }));
    expect(screen.getByTestId('kanban-detail-require-approval')).toBeTruthy();
  });

  it('shows checked state when require_approval is on', () => {
    renderSection(makeTask({ status: 'running', require_approval: true }));
    const checkbox = screen.getByTestId('kanban-detail-require-approval') as HTMLInputElement;
    expect(checkbox.checked).toBe(true);
  });

  it('calls handler on toggle with the new value', () => {
    const onChange = vi.fn();
    renderSection(makeTask({ status: 'ready', require_approval: false }), onChange);
    fireEvent.click(screen.getByTestId('kanban-detail-require-approval'));
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it('hides the checkbox and shows a read-only badge for IN_REVIEW tasks', () => {
    renderSection(makeTask({ status: 'in_review', require_approval: true }));
    expect(screen.queryByTestId('kanban-detail-require-approval')).toBeNull();
    expect(screen.getByText('requireApproval')).toBeTruthy();
  });

  it('renders nothing for locked statuses without require_approval', () => {
    renderSection(makeTask({ status: 'completed', require_approval: false }));
    expect(screen.queryByTestId('kanban-detail-require-approval')).toBeNull();
    expect(screen.queryByText('requireApproval')).toBeNull();
  });
});
