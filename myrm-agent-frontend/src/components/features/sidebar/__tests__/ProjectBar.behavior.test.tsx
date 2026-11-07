import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Project } from '@/services/projects';
import { useProjectStore } from '@/store/useProjectStore';
import ProjectBar from '../ProjectBar';

const api = vi.hoisted(() => ({
  getProjects: vi.fn(),
  createProject: vi.fn(),
  adoptProjectWorkspace: vi.fn(),
  updateProject: vi.fn(),
  deleteProject: vi.fn(),
}));
vi.mock('@/services/projects', () => api);

vi.mock('@/components/features/project-workspace/ProjectWorkspaceMount', () => ({
  default: ({ projectName, onOpenChange }: { projectName: string; onOpenChange: (open: boolean) => void }) => (
    <div data-testid="workspace-mount" data-project={projectName}>
      <button onClick={() => onOpenChange(false)}>close-mount</button>
    </div>
  ),
}));
vi.mock('@/components/features/project-workspace/ProjectWorkspaceAdoptDialog', () => ({
  default: () => <div data-testid="adopt-dialog" />,
}));
vi.mock('../ProjectDefaultAgentDialog', () => ({
  ProjectDefaultAgentDialog: ({ project }: { project: Project }) => (
    <div data-testid="default-agent" data-project={project.name} />
  ),
}));

const makeProject = (id: string, name: string, color: string): Project => ({
  id,
  name,
  description: '',
  color,
  sortOrder: 0,
  goalSummary: '',
  createdAt: null,
  updatedAt: null,
});

const atlas = makeProject('p1', 'Atlas', '#7cb9ff');
const growth = makeProject('p2', 'Growth', '#ff7eb3');

const seed = (projects: Project[], activeFilter: string | null | undefined = undefined) =>
  useProjectStore.setState({ projects, activeFilter, loaded: true });

const chip = (name: string) => screen.getByRole('button', { name });
const openMenu = (name: string) => fireEvent.contextMenu(chip(name), { clientX: 30, clientY: 40 });

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  seed([]);
});

describe('ProjectBar empty state', () => {
  it('offers to add the first project and opens the name field', () => {
    render(<ProjectBar />);

    fireEvent.click(screen.getByRole('button', { name: 'project.addFirst' }));

    expect(screen.getByPlaceholderText('project.namePlaceholder')).toHaveFocus();
  });
});

describe('ProjectBar chips', () => {
  it('lists All, Unassigned and every project', () => {
    seed([atlas, growth]);
    render(<ProjectBar />);

    for (const name of ['project.all', 'project.unassigned', 'Atlas', 'Growth']) {
      expect(chip(name)).toBeInTheDocument();
    }
  });

  it('loads the projects once when the store has not fetched them yet', async () => {
    api.getProjects.mockResolvedValue([atlas]);
    useProjectStore.setState({ projects: [], loaded: false });

    render(<ProjectBar />);

    await waitFor(() => expect(chip('Atlas')).toBeInTheDocument());
    expect(api.getProjects).toHaveBeenCalledTimes(1);
  });

  it('filters by a project and clears the filter when the same chip is clicked again', () => {
    seed([atlas, growth]);
    render(<ProjectBar />);

    fireEvent.click(chip('Atlas'));
    expect(useProjectStore.getState().activeFilter).toBe('p1');

    fireEvent.click(chip('Atlas'));
    expect(useProjectStore.getState().activeFilter).toBeUndefined();
  });

  it('switches between projects, Unassigned and All', () => {
    seed([atlas, growth], 'p1');
    render(<ProjectBar />);

    fireEvent.click(chip('Growth'));
    expect(useProjectStore.getState().activeFilter).toBe('p2');

    fireEvent.click(chip('project.unassigned'));
    expect(useProjectStore.getState().activeFilter).toBeNull();

    fireEvent.click(chip('project.unassigned'));
    expect(useProjectStore.getState().activeFilter).toBeUndefined();

    fireEvent.click(chip('Atlas'));
    fireEvent.click(chip('project.all'));
    expect(useProjectStore.getState().activeFilter).toBeUndefined();
  });
});

describe('ProjectBar new project field', () => {
  it('creates a project with the next palette color on Enter', async () => {
    api.createProject.mockResolvedValue(makeProject('p3', 'Docs', '#7afcb4'));
    seed([atlas, growth]);
    render(<ProjectBar />);

    fireEvent.click(screen.getByTitle('project.newProject'));
    const input = screen.getByPlaceholderText('project.namePlaceholder');
    fireEvent.change(input, { target: { value: '  Docs ' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => expect(api.createProject).toHaveBeenCalledTimes(1));
    expect(api.createProject.mock.calls[0].slice(0, 2)).toEqual(['Docs', '#7afcb4']);
    await waitFor(() => expect(screen.queryByPlaceholderText('project.namePlaceholder')).toBeNull());
    expect(chip('Docs')).toBeInTheDocument();
  });

  it('closes on Escape and on a blank name without creating anything', () => {
    seed([atlas]);
    render(<ProjectBar />);

    fireEvent.click(screen.getByTitle('project.newProject'));
    fireEvent.keyDown(screen.getByPlaceholderText('project.namePlaceholder'), { key: 'Escape' });
    expect(screen.queryByPlaceholderText('project.namePlaceholder')).toBeNull();

    fireEvent.click(screen.getByTitle('project.newProject'));
    fireEvent.blur(screen.getByPlaceholderText('project.namePlaceholder'));
    expect(screen.queryByPlaceholderText('project.namePlaceholder')).toBeNull();
    expect(api.createProject).not.toHaveBeenCalled();
  });

  it('opens the folder adoption dialog from the folder button', () => {
    seed([atlas]);
    render(<ProjectBar />);

    fireEvent.click(screen.getByTitle('project.workspaceMount.adoptFolder'));

    expect(screen.getByTestId('adopt-dialog')).toBeInTheDocument();
  });
});

describe('ProjectBar context menu', () => {
  beforeEach(() => {
    seed([atlas, growth]);
  });

  it('renames a project in place and saves on Enter', async () => {
    api.updateProject.mockResolvedValue({ ...atlas, name: 'Atlas 2' });
    render(<ProjectBar />);

    openMenu('Atlas');
    fireEvent.click(chip('project.rename'));
    const input = screen.getByDisplayValue('Atlas');
    expect(input).toHaveFocus();
    fireEvent.change(input, { target: { value: 'Atlas 2' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => expect(api.updateProject).toHaveBeenCalledWith('p1', { name: 'Atlas 2' }));
    await waitFor(() => expect(chip('Atlas 2')).toBeInTheDocument());
  });

  it('drops a rename on Escape', () => {
    render(<ProjectBar />);

    openMenu('Atlas');
    fireEvent.click(chip('project.rename'));
    fireEvent.keyDown(screen.getByDisplayValue('Atlas'), { key: 'Escape' });

    expect(screen.queryByDisplayValue('Atlas')).toBeNull();
    expect(chip('Atlas')).toBeInTheDocument();
    expect(api.updateProject).not.toHaveBeenCalled();
  });

  it('recolors a project from the palette and closes the menu', async () => {
    api.updateProject.mockResolvedValue({ ...atlas, color: '#ff7eb3' });
    render(<ProjectBar />);

    openMenu('Atlas');
    fireEvent.click(chip('#ff7eb3'));

    await waitFor(() => expect(api.updateProject).toHaveBeenCalledWith('p1', { color: '#ff7eb3' }));
    await waitFor(() => expect(screen.queryByRole('button', { name: 'project.rename' })).toBeNull());
  });

  it('marks the project color that is already chosen', () => {
    render(<ProjectBar />);

    openMenu('Atlas');

    expect(chip('#7cb9ff')).toHaveAttribute('aria-pressed', 'true');
    expect(chip('#ff7eb3')).toHaveAttribute('aria-pressed', 'false');
  });

  it('deletes a project and drops the filter that pointed at it', async () => {
    api.deleteProject.mockResolvedValue(undefined);
    seed([atlas, growth], 'p1');
    render(<ProjectBar />);

    openMenu('Atlas');
    fireEvent.click(chip('project.delete'));

    await waitFor(() => expect(api.deleteProject).toHaveBeenCalledWith('p1'));
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Atlas' })).toBeNull());
    expect(useProjectStore.getState().activeFilter).toBeUndefined();
  });

  it('opens the workspace dialog for the chosen project and closes it again', () => {
    render(<ProjectBar />);

    openMenu('Growth');
    fireEvent.click(chip('project.setWorkspace'));
    expect(screen.getByTestId('workspace-mount')).toHaveAttribute('data-project', 'Growth');

    fireEvent.click(chip('close-mount'));
    expect(screen.queryByTestId('workspace-mount')).toBeNull();
  });

  it('opens the default agent dialog for the chosen project', () => {
    render(<ProjectBar />);

    openMenu('Growth');
    fireEvent.click(chip('project.setDefaultAgent'));

    expect(screen.getByTestId('default-agent')).toHaveAttribute('data-project', 'Growth');
  });

  it('closes when the pointer goes down outside of it', () => {
    render(<ProjectBar />);

    openMenu('Atlas');
    expect(chip('project.rename')).toBeInTheDocument();
    fireEvent.mouseDown(document.body);

    expect(screen.queryByRole('button', { name: 'project.rename' })).toBeNull();
  });

  it('keeps the menu open while the pointer goes down inside of it', () => {
    render(<ProjectBar />);

    openMenu('Atlas');
    fireEvent.mouseDown(chip('project.rename'));

    expect(chip('project.rename')).toBeInTheDocument();
  });
});
