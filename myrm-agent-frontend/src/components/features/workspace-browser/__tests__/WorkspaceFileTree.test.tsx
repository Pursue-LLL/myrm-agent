/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { FileEntry } from '@/services/chat';
import { WorkspaceFileTreeItem } from '../WorkspaceFileTree';

const WORKSPACE = '/vault/chat-1';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/components/features/files/FileTypeIcon', () => ({
  FileTypeIcon: () => <span data-testid="file-icon" />,
}));

vi.mock('@/services/chat', () => ({
  renameInWorkspace: vi.fn(),
}));

const FILE: FileEntry = {
  name: 'Hello.ts',
  path: `${WORKSPACE}/Hello.ts`,
  type: 'file',
  size: 92,
  mtime: null,
  is_text: true,
  children: null,
};

const FOLDER: FileEntry = {
  ...FILE,
  name: 'src',
  path: `${WORKSPACE}/src`,
  type: 'directory',
  size: null,
  children: [],
};

function renderRow(node: FileEntry, extra: Partial<Parameters<typeof WorkspaceFileTreeItem>[0]> = {}) {
  const handlers = {
    onToggle: vi.fn(),
    onFileClick: vi.fn(),
    onMention: vi.fn(),
    onContextMenu: vi.fn(),
    onRenameComplete: vi.fn(),
    onRenameCancel: vi.fn(),
  };
  render(
    <WorkspaceFileTreeItem
      node={node}
      depth={0}
      expandedPaths={new Set()}
      loadingPaths={new Set()}
      renamingPath={null}
      workspace={WORKSPACE}
      {...handlers}
      {...extra}
    />,
  );
  return handlers;
}

const rowButton = (name: string): HTMLElement => screen.getByText(name).closest('button') as HTMLElement;

describe('WorkspaceFileTreeItem', () => {
  it('opens a file when its row is clicked', () => {
    const { onFileClick, onMention } = renderRow(FILE);

    fireEvent.click(rowButton('Hello.ts'));

    expect(onFileClick).toHaveBeenCalledWith(FILE);
    expect(onMention).not.toHaveBeenCalled();
  });

  it('toggles a folder when its row is clicked', () => {
    const { onToggle, onFileClick } = renderRow(FOLDER);

    fireEvent.click(rowButton('src'));

    expect(onToggle).toHaveBeenCalledWith(FOLDER);
    expect(onFileClick).not.toHaveBeenCalled();
  });

  it('references a file from the @ control without opening it', () => {
    const { onMention, onFileClick } = renderRow(FILE);

    fireEvent.click(screen.getByRole('button', { name: 'mentionFile' }));

    expect(onMention).toHaveBeenCalledWith(FILE);
    expect(onFileClick).not.toHaveBeenCalled();
  });

  it('keeps the @ control beside the row button instead of nesting a control inside it', () => {
    renderRow(FILE);

    expect(rowButton('Hello.ts').querySelector('button, [role="button"]')).toBeNull();
    expect(screen.getByRole('button', { name: 'mentionFile' }).closest('button')).not.toBe(rowButton('Hello.ts'));
  });

  it('opens the context menu from the @ control as well as from the row', () => {
    const { onContextMenu } = renderRow(FILE);

    fireEvent.contextMenu(rowButton('Hello.ts'));
    fireEvent.contextMenu(screen.getByRole('button', { name: 'mentionFile' }));

    expect(onContextMenu).toHaveBeenCalledTimes(2);
    expect(onContextMenu.mock.calls.every(([, node]) => node === FILE)).toBe(true);
  });

  it('offers no @ control on a folder', () => {
    renderRow(FOLDER);

    expect(screen.queryByRole('button', { name: 'mentionFile' })).toBeNull();
  });

  it('hides the @ control while its file is being renamed', () => {
    renderRow(FILE, { renamingPath: FILE.path });

    expect(screen.queryByRole('button', { name: 'mentionFile' })).toBeNull();
  });

  it('hides the @ control when the host provides no mention handler', () => {
    renderRow(FILE, { onMention: undefined });

    expect(screen.queryByRole('button', { name: 'mentionFile' })).toBeNull();
  });
});
