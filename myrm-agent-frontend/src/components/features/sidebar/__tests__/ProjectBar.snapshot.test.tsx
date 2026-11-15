import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { Project } from '@/services/projects';
import { flushSnapshot, resetSnapshotForTests, writeSnapshotSection } from '@/store/first-screen/envelope';
import { encodeProjects } from '@/store/first-screen/projectsSection';
import { resetSeedingForTests } from '@/store/first-screen/restore';
import { useProjectStore } from '@/store/useProjectStore';
import { deferred } from '@/test-utils/deferred';

import ProjectBar from '../ProjectBar';

const kit = vi.hoisted(() => ({
  snapshotEnabled: true,
  getProjects: vi.fn<() => Promise<Project[]>>(),
}));

vi.mock('@/services/projects', () => ({
  getProjects: kit.getProjects,
  createProject: vi.fn(),
  adoptProjectWorkspace: vi.fn(),
  updateProject: vi.fn(),
  deleteProject: vi.fn(),
}));
vi.mock('@/store/first-screen/gate', () => ({ isFirstScreenSnapshotEnabled: () => kit.snapshotEnabled }));
vi.mock('@/components/features/project-workspace/ProjectWorkspaceMount', () => ({ default: () => null }));
vi.mock('@/components/features/project-workspace/ProjectWorkspaceAdoptDialog', () => ({ default: () => null }));
vi.mock('../ProjectDefaultAgentDialog', () => ({ ProjectDefaultAgentDialog: () => null }));

const makeProject = (id: string, name: string): Project => ({
  id,
  name,
  description: '',
  color: '#7cb9ff',
  sortOrder: 0,
  goalSummary: '',
  createdAt: null,
  updatedAt: null,
});

const flush = () => act(async () => undefined);

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  resetSnapshotForTests();
  resetSeedingForTests();
  kit.snapshotEnabled = true;
  useProjectStore.setState({ projects: [], activeFilter: undefined, loaded: false });
  writeSnapshotSection('projects', encodeProjects([makeProject('p1', 'Stored Atlas')]));
  flushSnapshot();
});

afterEach(() => {
  resetSnapshotForTests();
});

describe('ProjectBar first-screen snapshot', () => {
  it('shows the stored projects while the fetch is pending and swaps in the fetched list', async () => {
    const answer = deferred<Project[]>();
    kit.getProjects.mockReturnValue(answer.promise);

    render(<ProjectBar />);
    await flush();

    expect(screen.getByRole('button', { name: 'Stored Atlas' })).toBeInTheDocument();
    expect(kit.getProjects).toHaveBeenCalledTimes(1);

    await act(async () => answer.resolve([makeProject('p2', 'Fetched Growth')]));

    expect(screen.getByRole('button', { name: 'Fetched Growth' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Stored Atlas' })).not.toBeInTheDocument();
    expect(useProjectStore.getState().loaded).toBe(true);
  });

  it('still fetches when the stored projects are on screen', async () => {
    kit.getProjects.mockReturnValue(deferred<Project[]>().promise);

    render(<ProjectBar />);
    await flush();

    expect(useProjectStore.getState().loaded).toBe(false);
    expect(kit.getProjects).toHaveBeenCalledTimes(1);
  });

  it('shows no project chips when the feature is off', async () => {
    kit.snapshotEnabled = false;
    kit.getProjects.mockReturnValue(deferred<Project[]>().promise);

    render(<ProjectBar />);
    await flush();

    expect(screen.queryByRole('button', { name: 'Stored Atlas' })).not.toBeInTheDocument();
  });
});
