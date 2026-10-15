import { describe, it, expect, vi } from 'vitest';
import type { ComponentProps } from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { KanbanTask, TaskStatus } from '@/services/kanban';
import blockedReasons from '@shared/config/kanban_blocked_reasons.json';
import { TaskDetailsSection } from '../KanbanTaskDrawerDetails';

const stableT = (key: string) => key;

vi.mock('../KanbanMarkdown', () => ({
  default: ({ children }: { children: string }) => <span>{children}</span>,
}));

vi.mock('@/services/kanban', () => ({
  KANBAN_SOURCE_CHAT_METADATA_KEY: 'source_chat_id',
  hasKanbanCompletionIntent: () => false,
  completionCriteriaToText: (value: unknown) => String(value ?? ''),
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

type SectionProps = ComponentProps<typeof TaskDetailsSection>;

function renderSection(
  task: KanbanTask,
  onRequireApprovalChange = vi.fn(),
  editingSkills = false,
  overrides: Partial<SectionProps> = {},
) {
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
      editingSkills={editingSkills}
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
      {...overrides}
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

describe('TaskDetailsSection running skill notice', () => {
  it('shows a notice when editing skills on a running task', () => {
    renderSection(makeTask({ status: 'running' }), vi.fn(), true);
    expect(screen.getByText('skillsRunningNotice')).toBeTruthy();
  });

  it('hides the notice for non-running tasks', () => {
    renderSection(makeTask({ status: 'ready' }), vi.fn(), true);
    expect(screen.queryByText('skillsRunningNotice')).toBeNull();
  });
});

describe('TaskDetailsSection blocked reason', () => {
  const blockedTask = (reason: string) => makeTask({ status: 'blocked', block_kind: 'human', blocked_reason: reason });

  it('shows a dependency merge failure in the interface language', () => {
    renderSection(blockedTask(blockedReasons.parentMergeFailed));
    expect(screen.getByText('blockedReason.parentMergeFailed')).toBeTruthy();
    expect(screen.queryByText(/Merging a dependency/)).toBeNull();
  });

  it('shows any other reason as written', () => {
    renderSection(blockedTask('Waiting for the reviewer'));
    expect(screen.getByText('Waiting for the reviewer')).toBeTruthy();
  });
});

describe('TaskDetailsSection inline editors', () => {
  it('opens the timeout editor from a native button', async () => {
    const setEditingTimeout = vi.fn();
    const setTimeoutValue = vi.fn();
    renderSection(makeTask({ max_runtime_seconds: 300 }), vi.fn(), false, { setEditingTimeout, setTimeoutValue });

    const chip = screen.getByRole('button', { name: /^timeoutLabel:/ });
    expect(chip.tagName).toBe('BUTTON');
    expect(chip.getAttribute('type')).toBe('button');

    await userEvent.click(chip);
    expect(setTimeoutValue).toHaveBeenCalledWith(300);
    expect(setEditingTimeout).toHaveBeenCalledWith(true);
  });

  it('opens the skills editor from a native button that lists every skill', async () => {
    const setEditingSkills = vi.fn();
    const setSkillsText = vi.fn();
    renderSection(makeTask({ extra_skill_ids: ['web-search', 'code-review'] }), vi.fn(), false, {
      setEditingSkills,
      setSkillsText,
    });

    const chip = screen.getByText('web-search').closest('button') as HTMLButtonElement;
    expect(chip.textContent).toContain('code-review');
    expect(chip.tagName).toBe('BUTTON');

    await userEvent.click(chip);
    expect(setSkillsText).toHaveBeenCalledWith('web-search, code-review');
    expect(setEditingSkills).toHaveBeenCalledWith(true);
  });

  it('opens the model editor from a native button', async () => {
    const setEditingModel = vi.fn();
    const setModelValue = vi.fn();
    renderSection(makeTask({ model_override: 'openai/gpt-5' }), vi.fn(), false, { setEditingModel, setModelValue });

    const chip = screen.getByRole('button', { name: /^modelLabel: openai\/gpt-5$/ });
    expect(chip.tagName).toBe('BUTTON');

    await userEvent.click(chip);
    expect(setModelValue).toHaveBeenCalledWith('openai/gpt-5');
    expect(setEditingModel).toHaveBeenCalledWith(true);
  });

  it('keeps the criteria card keyboard-operable: Enter and Space open the editor', async () => {
    const setEditingCriteria = vi.fn();
    const setCriteriaText = vi.fn();
    renderSection(makeTask({ completion_criteria: 'tests pass' }), vi.fn(), false, {
      setEditingCriteria,
      setCriteriaText,
    });

    const card = screen.getByText('tests pass').closest('[role="button"]') as HTMLElement;
    expect(card.tabIndex).toBe(0);

    card.focus();
    await userEvent.keyboard('{Enter}');
    expect(setCriteriaText).toHaveBeenLastCalledWith('tests pass');
    expect(setEditingCriteria).toHaveBeenCalledTimes(1);

    await userEvent.keyboard(' ');
    expect(setEditingCriteria).toHaveBeenCalledTimes(2);
  });
});
