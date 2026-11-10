import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { AgentListItem } from '@/services/agent';
import type { Project } from '@/services/projects';
import { deferred } from '@/test-utils/deferred';

const mocks = vi.hoisted(() => ({
  // One translator for the whole file: a new function per render would re-run every effect that lists `t`.
  t: (key: string) => key,
  toast: vi.fn(),
  updateProject: vi.fn<(projectId: string, patch: { default_agent_id: string | null }) => Promise<void>>(),
  fetchAgents: vi.fn<(forceRefresh?: boolean) => Promise<void>>(),
  agentState: { agents: [] as AgentListItem[], loading: false },
}));

vi.mock('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: () => mocks.t,
}));
vi.mock('@/hooks/shared/useToast', () => ({ useToast: () => ({ toast: mocks.toast }) }));
vi.mock('@/store/useProjectStore', () => ({ useProjectStore: () => ({ updateProject: mocks.updateProject }) }));
vi.mock('@/store/useAgentStore', () => ({
  default: () => ({ ...mocks.agentState, fetchAgents: mocks.fetchAgents }),
}));
vi.mock('@/components/agent/AgentAvatar', () => ({ AgentAvatar: () => null }));
vi.mock('@/components/agent/builtin-agent-i18n', () => ({
  getBuiltinAgentName: (_agentId: string, name: string) => name,
}));

import { ProjectDefaultAgentDialog } from '../ProjectDefaultAgentDialog';

const STAMP = '2026-01-01T00:00:00Z';

function agent(id: string, name: string): AgentListItem {
  return { id, name, created_at: STAMP, updated_at: STAMP };
}

function projectWith(defaultAgentId?: string): Project {
  return {
    id: 'project-1',
    name: 'Project',
    description: '',
    color: 'blue',
    sortOrder: 0,
    defaultAgentId,
    goalSummary: '',
    createdAt: STAMP,
    updatedAt: STAMP,
  };
}

const onOpenChange = vi.fn<(open: boolean) => void>();

function dialog(open: boolean, project: Project = projectWith('a')) {
  return <ProjectDefaultAgentDialog open={open} onOpenChange={onOpenChange} project={project} />;
}

const optionButton = (name: string) => screen.getByRole('button', { name });
const isChosen = (name: string) => optionButton(name).className.includes('bg-accent');
const saveButton = () => screen.getByRole('button', { name: 'common.save' });

beforeEach(() => {
  vi.resetAllMocks();
  mocks.fetchAgents.mockResolvedValue(undefined);
  mocks.updateProject.mockResolvedValue(undefined);
  mocks.agentState.agents = [agent('a', 'Agent A'), agent('b', 'Agent B')];
  mocks.agentState.loading = false;
});

describe('ProjectDefaultAgentDialog', () => {
  it('reloads the roster every time the dialog opens and not while it stays closed', () => {
    const view = render(dialog(false));
    expect(mocks.fetchAgents).not.toHaveBeenCalled();

    view.rerender(dialog(true));
    expect(mocks.fetchAgents).toHaveBeenCalledTimes(1);
    expect(mocks.fetchAgents).toHaveBeenLastCalledWith(true);

    view.rerender(dialog(false));
    expect(mocks.fetchAgents).toHaveBeenCalledTimes(1);

    view.rerender(dialog(true));
    expect(mocks.fetchAgents).toHaveBeenCalledTimes(2);
  });

  it('shows the saved default agent as chosen and nothing to save yet', () => {
    render(dialog(true, projectWith('a')));

    expect(isChosen('Agent A')).toBe(true);
    expect(isChosen('Agent B')).toBe(false);
    expect(isChosen('project.defaultAgent.none')).toBe(false);
    expect(saveButton()).toBeDisabled();
  });

  it('chooses the "none" entry for a project without a default agent', () => {
    render(dialog(true, projectWith()));

    expect(isChosen('project.defaultAgent.none')).toBe(true);
    expect(isChosen('Agent A')).toBe(false);
    expect(saveButton()).toBeDisabled();
  });

  it('lets another agent be picked and picking the saved one again leaves nothing to save', () => {
    render(dialog(true, projectWith('a')));

    fireEvent.click(optionButton('Agent B'));
    expect(isChosen('Agent B')).toBe(true);
    expect(isChosen('Agent A')).toBe(false);
    expect(saveButton()).toBeEnabled();

    fireEvent.click(optionButton('Agent A'));
    expect(isChosen('Agent A')).toBe(true);
    expect(saveButton()).toBeDisabled();
  });

  it('keeps the pick across re-renders while the dialog stays open', () => {
    const view = render(dialog(true, projectWith('a')));
    fireEvent.click(optionButton('Agent B'));

    view.rerender(dialog(true, projectWith('a')));

    expect(isChosen('Agent B')).toBe(true);
  });

  it('forgets a pick that was never saved when the dialog opens again', () => {
    const view = render(dialog(true, projectWith('a')));
    fireEvent.click(optionButton('Agent B'));

    view.rerender(dialog(false, projectWith('a')));
    view.rerender(dialog(true, projectWith('a')));

    expect(isChosen('Agent A')).toBe(true);
    expect(isChosen('Agent B')).toBe(false);
  });

  it('follows a new saved default while nothing was picked', () => {
    const view = render(dialog(true, projectWith('a')));

    view.rerender(dialog(true, projectWith('b')));

    expect(isChosen('Agent B')).toBe(true);
    expect(isChosen('Agent A')).toBe(false);
  });

  it('saves the pick on the project and closes the dialog', async () => {
    render(dialog(true, projectWith('a')));
    fireEvent.click(optionButton('Agent B'));

    fireEvent.click(saveButton());

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(mocks.updateProject).toHaveBeenCalledWith('project-1', { default_agent_id: 'b' });
    expect(mocks.toast).not.toHaveBeenCalled();
  });

  it('blocks a second save while the first one is still running', async () => {
    const pending = deferred<void>();
    mocks.updateProject.mockReturnValue(pending.promise);
    render(dialog(true, projectWith('a')));
    fireEvent.click(optionButton('Agent B'));

    fireEvent.click(saveButton());
    await waitFor(() => expect(saveButton()).toBeDisabled());
    fireEvent.click(saveButton());
    expect(mocks.updateProject).toHaveBeenCalledTimes(1);

    pending.resolve();
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it('clears the default agent when "none" is saved', async () => {
    render(dialog(true, projectWith('a')));
    fireEvent.click(optionButton('project.defaultAgent.none'));

    fireEvent.click(saveButton());

    await waitFor(() => expect(mocks.updateProject).toHaveBeenCalledWith('project-1', { default_agent_id: null }));
  });

  it('keeps the dialog open and tells the user when saving fails', async () => {
    mocks.updateProject.mockRejectedValue(new Error('server said no'));
    render(dialog(true, projectWith('a')));
    fireEvent.click(optionButton('Agent B'));

    fireEvent.click(saveButton());

    await waitFor(() =>
      expect(mocks.toast).toHaveBeenCalledWith({
        title: 'project.defaultAgent.saveFailed',
        description: 'server said no',
        variant: 'destructive',
      }),
    );
    expect(onOpenChange).not.toHaveBeenCalled();
    await waitFor(() => expect(saveButton()).toBeEnabled());
    expect(isChosen('Agent B')).toBe(true);
  });

  it('describes a failure that is not an Error by its text', async () => {
    mocks.updateProject.mockRejectedValue('offline');
    render(dialog(true, projectWith('a')));
    fireEvent.click(optionButton('Agent B'));

    fireEvent.click(saveButton());

    await waitFor(() => expect(mocks.toast).toHaveBeenCalledWith(expect.objectContaining({ description: 'offline' })));
  });

  it('shows a spinner instead of the agents while the roster loads', () => {
    mocks.agentState.loading = true;
    render(dialog(true, projectWith('a')));

    expect(screen.queryByRole('button', { name: 'Agent A' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'project.defaultAgent.none' })).not.toBeInTheDocument();
  });

  it('closes through the cancel button without saving', () => {
    render(dialog(true, projectWith('a')));

    fireEvent.click(screen.getByRole('button', { name: 'common.cancel' }));

    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(mocks.updateProject).not.toHaveBeenCalled();
  });
});
