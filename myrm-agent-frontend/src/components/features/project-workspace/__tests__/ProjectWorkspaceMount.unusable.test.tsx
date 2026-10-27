import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import ProjectWorkspaceMount from '../ProjectWorkspaceMount';

vi.mock('@/services/projects', () => ({ updateProject: vi.fn() }));
vi.mock('@/services/chat', () => ({ browseDirectories: vi.fn() }));
vi.mock('@/services/workspaceTrust', () => ({ previewWorkspaceTrustManifest: vi.fn() }));
vi.mock('@/hooks/shared/useToast', () => ({ toast: vi.fn() }));
vi.mock('@/lib/tauri', () => ({ isTauriEnvironment: () => false }));
vi.mock('../WorkspaceTrustFolderGate', () => ({ default: () => null }));

function mount(props: { initialPath?: string | null; workspaceUsable?: boolean }) {
  return render(
    <ProjectWorkspaceMount
      projectId="p1"
      projectName="Notes"
      open
      onOpenChange={vi.fn()}
      onBound={vi.fn()}
      {...props}
    />,
  );
}

describe('ProjectWorkspaceMount unusable folder notice', () => {
  it('tells the user when the linked folder is too broad to work in', () => {
    mount({ initialPath: '/Users/me', workspaceUsable: false });
    expect(screen.getByRole('alert').textContent).toContain('unusableHint');
  });

  it('stays quiet for a usable folder', () => {
    mount({ initialPath: '/Users/me/notes', workspaceUsable: true });
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('defaults to usable, so a payload without the flag shows no notice', () => {
    mount({ initialPath: '/Users/me/notes' });
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('shows nothing when no folder is linked', () => {
    mount({ initialPath: null, workspaceUsable: false });
    expect(screen.queryByRole('alert')).toBeNull();
  });
});
