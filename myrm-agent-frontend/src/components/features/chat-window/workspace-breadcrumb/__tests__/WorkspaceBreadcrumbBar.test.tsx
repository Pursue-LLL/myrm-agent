/**
 * [INPUT]
 * - @testing-library/react (POS: React Component Testing)
 * - @/components/features/chat-window/workspace-breadcrumb/WorkspaceBreadcrumbBar
 * - @/components/features/chat-window/workspace-breadcrumb/useWorkspaceBreadcrumbStore
 *
 * [OUTPUT]
 * - Component unit tests for WorkspaceBreadcrumbBar UI rendering and user interactions.
 */

import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { WorkspaceBreadcrumbBar } from '../WorkspaceBreadcrumbBar';
import { useWorkspaceBreadcrumbStore } from '../useWorkspaceBreadcrumbStore';

describe('WorkspaceBreadcrumbBar Component', () => {
  beforeEach(() => {
    useWorkspaceBreadcrumbStore.getState().resetStore();
    vi.restoreAllMocks();
  });

  it('should render physical workspace badge and path segments', () => {
    render(<WorkspaceBreadcrumbBar overridePath="/Users/dev/my-project" />);

    expect(screen.getByTestId('workspace-breadcrumb-bar')).toBeInTheDocument();
    expect(screen.getByTestId('workspace-badge')).toHaveTextContent('物理工作区');
    expect(screen.getByText('my-project')).toBeInTheDocument();
  });

  it('should render sandbox badge when path indicates isolated container', () => {
    render(<WorkspaceBreadcrumbBar overridePath="/sandbox/isolated-app" />);

    expect(screen.getByTestId('workspace-badge')).toHaveTextContent('沙箱隔离');
    expect(screen.getByText('isolated-app')).toBeInTheDocument();
  });

  it('should handle copy path button click with feedback', async () => {
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    render(<WorkspaceBreadcrumbBar overridePath="/Users/alice/projects/demo" />);

    const copyBtn = screen.getByTestId('btn-copy-path');
    fireEvent.click(copyBtn);

    await waitFor(() => {
      expect(writeTextMock).toHaveBeenCalledWith('/Users/alice/projects/demo');
    });
  });

  it('should trigger reveal in finder and terminal on button clicks', () => {
    const store = useWorkspaceBreadcrumbStore.getState();
    const finderSpy = vi.spyOn(store, 'revealInFinder');
    const terminalSpy = vi.spyOn(store, 'revealInTerminal');

    render(<WorkspaceBreadcrumbBar overridePath="/Users/bob/repo" />);

    const finderBtn = screen.getByTestId('btn-reveal-finder');
    fireEvent.click(finderBtn);
    expect(useWorkspaceBreadcrumbStore.getState().lastRevealedAction).toBe('finder');

    const terminalBtn = screen.getByTestId('btn-reveal-terminal');
    fireEvent.click(terminalBtn);
    expect(useWorkspaceBreadcrumbStore.getState().lastRevealedAction).toBe('terminal');

    finderSpy.mockRestore();
    terminalSpy.mockRestore();
  });

  it('should respect maxVisibleSegments truncation', () => {
    render(
      <WorkspaceBreadcrumbBar
        overridePath="/a/b/c/d/e/f"
        maxVisibleSegments={3}
      />,
    );

    expect(screen.getByText('...')).toBeInTheDocument();
    expect(screen.getByText('f')).toBeInTheDocument();
  });
});
