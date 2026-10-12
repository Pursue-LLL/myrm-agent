/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { WorkAssetSidebar } from '../WorkAssetSidebar';
import { useWorkLayoutStore } from '@/store/useWorkLayoutStore';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

describe('WorkAssetSidebar component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useWorkLayoutStore.setState({
      workSidebarTab: 'tasks',
      isSidebarCollapsed: false,
      activeTaskId: 'task-1',
      tasks: [
        {
          id: 'task-1',
          title: 'Cross-module dependency analysis',
          status: 'in_progress',
          progressPercentage: 50,
          subtasks: [
            { id: 'sub-1', title: 'Scan import hierarchy', completed: true },
            { id: 'sub-2', title: 'Verify cyclic dependencies', completed: false },
          ],
        },
      ],
    });
  });

  it('renders default tasks tab with task cards and subtasks checklist', () => {
    render(<WorkAssetSidebar />);

    expect(screen.getByText('tabTasks')).toBeDefined();
    expect(screen.getByText('tabSkills')).toBeDefined();
    expect(screen.getByText('tabConnectors')).toBeDefined();
    expect(screen.getByText('tabPartners')).toBeDefined();

    expect(screen.getByText('Cross-module dependency analysis')).toBeDefined();
    expect(screen.getByText('50%')).toBeDefined();
    expect(screen.getByText('Scan import hierarchy')).toBeDefined();
    expect(screen.getByText('Verify cyclic dependencies')).toBeDefined();
  });

  it('toggles subtask status when clicking a checklist item', () => {
    render(<WorkAssetSidebar />);

    const subtaskBtn = screen.getByRole('button', { name: /Verify cyclic dependencies/i });
    fireEvent.click(subtaskBtn);

    const task = useWorkLayoutStore.getState().tasks.find((t) => t.id === 'task-1');
    expect(task?.subtasks[1].completed).toBe(true);
    expect(task?.progressPercentage).toBe(100);
  });

  it('switches to skills tab, filters by search, and dispatches invocation event', () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
    render(<WorkAssetSidebar />);

    const skillsTabBtn = screen.getByRole('button', { name: /tabSkills/i });
    fireEvent.click(skillsTabBtn);

    expect(useWorkLayoutStore.getState().workSidebarTab).toBe('skills');
    expect(screen.getByText('Code Interpreter')).toBeDefined();
    expect(screen.getByText('Web Navigator')).toBeDefined();

    // Filter by search
    const searchInput = screen.getByPlaceholderText('skills.searchPlaceholder');
    fireEvent.change(searchInput, { target: { value: 'Interpreter' } });

    expect(screen.getByText('Code Interpreter')).toBeDefined();
    expect(screen.queryByText('Web Navigator')).toBeNull();

    // Click invoke action
    const invokeBtn = screen.getByRole('button', { name: /skills.triggerAction/i });
    fireEvent.click(invokeBtn);

    expect(dispatchSpy).toHaveBeenCalled();
    const event = dispatchSpy.mock.calls[0][0] as CustomEvent;
    expect(event.type).toBe('myrm:insert-to-chat');
    expect(event.detail.text).toContain('/skill run Code Interpreter');
  });

  it('switches to connectors and partners tabs successfully', () => {
    render(<WorkAssetSidebar />);

    // Connectors tab
    const connTabBtn = screen.getByRole('button', { name: /tabConnectors/i });
    fireEvent.click(connTabBtn);
    expect(screen.getByText('GitHub Integration')).toBeDefined();
    expect(screen.getByText('PostgreSQL Bridge')).toBeDefined();

    // Partners tab
    const partTabBtn = screen.getByRole('button', { name: /tabPartners/i });
    fireEvent.click(partTabBtn);
    expect(screen.getByText('Architect Agent')).toBeDefined();
    expect(screen.getByText('Code Reviewer')).toBeDefined();
  });

  it('toggles sidebar collapsed and expanded state', () => {
    render(<WorkAssetSidebar />);

    const collapseBtn = screen.getByTitle('sidebarCollapse');
    fireEvent.click(collapseBtn);

    expect(useWorkLayoutStore.getState().isSidebarCollapsed).toBe(true);

    const expandBtn = screen.getByTitle('sidebarExpand');
    fireEvent.click(expandBtn);

    expect(useWorkLayoutStore.getState().isSidebarCollapsed).toBe(false);
  });
});
