/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { FileEntry } from '@/services/chat';
import useChatStore from '@/store/useChatStore';
import { WorkspaceFileBrowser } from '../WorkspaceFileBrowser';

const WORKSPACE = '/vault/project';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

vi.mock('@/components/features/files/FileTypeIcon', () => ({
  FileTypeIcon: () => <span data-testid="file-icon" />,
}));

vi.mock('@/services/chat', () => ({
  uploadToWorkspace: vi.fn(),
  mkdirInWorkspace: vi.fn(),
  renameInWorkspace: vi.fn(),
  deleteInWorkspace: vi.fn(),
}));

const file = (name: string): FileEntry => ({
  name,
  path: `${WORKSPACE}/${name}`,
  type: 'file',
  size: 1,
  mtime: null,
  is_text: true,
  children: null,
});

const onLoadChildren = async (): Promise<void> => {};

const browser = (props: Partial<React.ComponentProps<typeof WorkspaceFileBrowser>> = {}) => (
  <WorkspaceFileBrowser workspacePath={WORKSPACE} files={[]} onLoadChildren={onLoadChildren} {...props} />
);

/** The big spinner of an empty, loading browser; the header's refresh button spins on its own. */
const contentSpinner = (container: HTMLElement): Element | null => container.querySelector('.py-8 .animate-spin');

describe('WorkspaceFileBrowser while a scan runs', () => {
  it('shows a spinner instead of the empty notice while the first scan has no tree yet', () => {
    const { container } = render(browser({ loading: true }));

    expect(contentSpinner(container)).not.toBeNull();
    expect(screen.queryByText('emptyDir')).toBeNull();
  });

  it('keeps the tree on screen during a refresh, row for row', () => {
    const { container, rerender } = render(browser({ files: [file('a.ts'), file('b.ts')] }));
    const row = screen.getByText('a.ts');

    rerender(browser({ files: [file('a.ts'), file('b.ts')], loading: true }));

    expect(contentSpinner(container)).toBeNull();
    expect(screen.getByText('a.ts')).toBe(row);
    expect(screen.getByText('b.ts')).toBeTruthy();
  });

  it('keeps a name being typed for a rename when a refresh swaps the tree', () => {
    const { rerender } = render(browser({ files: [file('a.ts')] }));
    fireEvent.contextMenu(screen.getByText('a.ts'));
    fireEvent.click(screen.getByText('rename'));
    const input = screen.getByDisplayValue('a.ts');
    fireEvent.change(input, { target: { value: 'draft-name.ts' } });

    rerender(browser({ files: [file('a.ts'), file('new.ts')], loading: true }));

    expect(screen.getByDisplayValue('draft-name.ts')).toBe(input);
  });

  it('shows an empty folder as empty once a scan has finished', () => {
    render(browser());

    expect(screen.getByText('emptyDir')).toBeTruthy();
  });
});

describe('WorkspaceFileBrowser when a scan fails', () => {
  it('words the failure in the user language and never shows the server text', () => {
    render(browser({ error: 'ECONNREFUSED 127.0.0.1:8080' }));

    expect(screen.getByText('folderLoadFailed')).toBeTruthy();
    expect(screen.queryByText(/ECONNREFUSED/)).toBeNull();
  });
});

describe('WorkspaceFileBrowser header name', () => {
  beforeEach(() => {
    useChatStore.setState({ chatId: undefined });
  });

  const header = (path: string) => screen.getByTitle(path);

  it('names the chat workspace in the user language instead of by its folder id', () => {
    useChatStore.setState({ chatId: 'abc-123' });
    const path = '/home/me/.myrm/workspaces/chat_abc-123';

    render(browser({ workspacePath: path }));

    expect(header(path).textContent).toBe('sessionWorkspace');
  });

  it('keeps the name of a folder the user made, even when it starts with chat_', () => {
    useChatStore.setState({ chatId: 'abc-123' });

    render(browser({ workspacePath: '/home/me/chat_notes' }));

    expect(header('/home/me/chat_notes').textContent).toBe('chat_notes');
  });

  it('shows the folder name when there is no current chat to compare with', () => {
    render(browser({ workspacePath: '/home/me/.myrm/workspaces/chat_abc-123' }));

    expect(header('/home/me/.myrm/workspaces/chat_abc-123').textContent).toBe('chat_abc-123');
  });

  it.each([
    ['/home/me/project', 'project'],
    ['/home/me/project/', 'project'],
    ['C:\\Users\\me\\project', 'project'],
    ['C:\\Users\\me\\project\\', 'project'],
    ['/', '/'],
  ])('shows %s as %s', (path, name) => {
    render(browser({ workspacePath: path }));

    expect(header(path).textContent).toBe(name);
  });
});
