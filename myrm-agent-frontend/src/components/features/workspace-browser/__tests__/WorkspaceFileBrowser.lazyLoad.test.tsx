/** @vitest-environment jsdom */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { FileEntry } from '@/services/chat';
import { WorkspaceFileBrowser } from '../WorkspaceFileBrowser';

const WORKSPACE = '/vault/chat-1';

const stableT = (key: string) => key;
const toastError = vi.hoisted(() => vi.fn());

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('sonner', () => ({
  toast: { error: toastError, success: vi.fn() },
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

const dir = (name: string, children: FileEntry[] | null): FileEntry => ({
  name,
  path: `${WORKSPACE}/${name}`,
  type: 'directory',
  size: null,
  mtime: null,
  is_text: null,
  children,
});

const FILES: FileEntry[] = [dir('scanned', [dir('boundary', null)]), dir('loaded', [])];

function deferred() {
  let resolve!: () => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<void>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const rowOf = (name: string): HTMLElement => {
  const row = screen.getByText(name).closest('button');
  if (!row) {
    throw new Error(`no row for ${name}`);
  }
  return row;
};

const isSpinning = (name: string): boolean => rowOf(name).querySelector('.animate-spin') !== null;

function openBoundaryFolder(onLoadChildren: (dirPath: string) => Promise<void>): void {
  render(<WorkspaceFileBrowser workspacePath={WORKSPACE} files={FILES} onLoadChildren={onLoadChildren} />);
  fireEvent.click(screen.getByText('scanned'));
  fireEvent.click(screen.getByText('boundary'));
}

describe('WorkspaceFileBrowser folder loading', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('loads the contents of a folder the scan did not reach when it is opened', async () => {
    const onLoadChildren = vi.fn(async () => {});

    openBoundaryFolder(onLoadChildren);
    await act(async () => {});

    expect(onLoadChildren).toHaveBeenCalledTimes(1);
    expect(onLoadChildren).toHaveBeenCalledWith(`${WORKSPACE}/boundary`);
  });

  it('shows a spinner on the folder while it loads and clears it afterwards', async () => {
    const loading = deferred();

    openBoundaryFolder(() => loading.promise);

    expect(isSpinning('boundary')).toBe(true);

    await act(async () => {
      loading.resolve();
    });

    expect(isSpinning('boundary')).toBe(false);
  });

  it('does not load folders whose contents are already known', () => {
    const onLoadChildren = vi.fn(async () => {});
    render(<WorkspaceFileBrowser workspacePath={WORKSPACE} files={FILES} onLoadChildren={onLoadChildren} />);

    fireEvent.click(screen.getByText('scanned'));
    fireEvent.click(screen.getByText('loaded'));

    expect(onLoadChildren).not.toHaveBeenCalled();
  });

  it('asks only once while the same folder is still loading', async () => {
    const loading = deferred();
    const onLoadChildren = vi.fn(() => loading.promise);
    openBoundaryFolder(onLoadChildren);

    fireEvent.click(screen.getByText('boundary'));
    fireEvent.click(screen.getByText('boundary'));

    expect(onLoadChildren).toHaveBeenCalledTimes(1);
    await act(async () => {
      loading.resolve();
    });
  });

  it('tells the user in their language and closes the folder again when it cannot be loaded', async () => {
    const loading = deferred();

    openBoundaryFolder(() => loading.promise);
    expect(isSpinning('boundary')).toBe(true);

    await act(async () => {
      loading.reject(new Error('ECONNREFUSED 127.0.0.1:8080'));
    });

    expect(toastError).toHaveBeenCalledTimes(1);
    expect(toastError).toHaveBeenCalledWith('folderLoadFailed');
    expect(isSpinning('boundary')).toBe(false);
    const chevron = rowOf('boundary').querySelector('svg');
    expect(chevron).not.toBeNull();
    expect(chevron?.getAttribute('class')).not.toContain('rotate-90');
  });
});
