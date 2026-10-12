/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MobileTaskSpawnForm } from '../MobileTaskSpawnForm';
import type { SpawnOptionAgent, SpawnOptionProject } from '@/services/remoteAccess';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
  useLocale: () => 'zh',
}));

vi.mock('@/components/agent/builtin-agent-i18n', () => ({
  getBuiltinAgentName: (_id: string, name: string) => name,
}));

vi.mock('@/lib/utils/imeUtils', () => ({
  isImeComposing: (e: { nativeEvent?: { isComposing?: boolean }; keyCode?: number }) =>
    Boolean(e.nativeEvent?.isComposing) || e.keyCode === 229,
}));

describe('MobileTaskSpawnForm', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockAgents: SpawnOptionAgent[] = [
    { id: 'agent-1', name: 'General Agent', avatar: null },
    { id: 'agent-2', name: 'Coding Agent', avatar: null },
  ];

  const mockProjects: SpawnOptionProject[] = [
    { id: 'proj-1', name: 'Project Alpha', color: null },
  ];

  it('toggles form visibility and calls onOpenOptions', () => {
    const onOpenOptions = vi.fn();
    render(
      <MobileTaskSpawnForm
        agents={mockAgents}
        projects={mockProjects}
        slotsFull={false}
        submitting={false}
        selectedAgentId="agent-1"
        onSelectAgent={vi.fn()}
        selectedProjectId=""
        onSelectProject={vi.fn()}
        taskMessage=""
        onTaskMessageChange={vi.fn()}
        onSubmit={vi.fn().mockResolvedValue(undefined)}
        onOpenOptions={onOpenOptions}
      />
    );

    const toggleBtn = screen.getByRole('button', { name: /newTask/i });
    expect(screen.queryByPlaceholderText('taskPlaceholder')).not.toBeInTheDocument();

    // Open
    fireEvent.click(toggleBtn);
    expect(onOpenOptions).toHaveBeenCalledTimes(1);
    expect(screen.getByPlaceholderText('taskPlaceholder')).toBeInTheDocument();
  });

  it('triggers onSubmit on button click or Enter keydown', () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    const onTaskMessageChange = vi.fn();
    const onSelectAgent = vi.fn();

    render(
      <MobileTaskSpawnForm
        agents={mockAgents}
        projects={mockProjects}
        slotsFull={false}
        submitting={false}
        selectedAgentId="agent-1"
        onSelectAgent={onSelectAgent}
        selectedProjectId=""
        onSelectProject={vi.fn()}
        taskMessage="Research autonomous agent architecture"
        onTaskMessageChange={onTaskMessageChange}
        onSubmit={onSubmit}
        onOpenOptions={vi.fn()}
      />
    );

    // Open form first
    fireEvent.click(screen.getByRole('button', { name: /newTask/i }));

    const submitBtn = screen.getByRole('button', { name: 'submit' });
    expect(submitBtn).not.toBeDisabled();

    // Click submit
    fireEvent.click(submitBtn);
    expect(onSubmit).toHaveBeenCalledTimes(1);

    // Enter keydown in textarea
    const textarea = screen.getByPlaceholderText('taskPlaceholder');
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });
    expect(onSubmit).toHaveBeenCalledTimes(2);

    // Shift+Enter should not submit
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: true });
    expect(onSubmit).toHaveBeenCalledTimes(2);
  });

  it('disables submit when slots are full or submitting', () => {
    render(
      <MobileTaskSpawnForm
        agents={mockAgents}
        projects={mockProjects}
        slotsFull={true}
        submitting={false}
        selectedAgentId="agent-1"
        onSelectAgent={vi.fn()}
        selectedProjectId=""
        onSelectProject={vi.fn()}
        taskMessage="Do something"
        onTaskMessageChange={vi.fn()}
        onSubmit={vi.fn().mockResolvedValue(undefined)}
        onOpenOptions={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /newTask/i }));
    const submitBtn = screen.getByRole('button', { name: 'submit' });
    expect(submitBtn).toBeDisabled();
  });
});
