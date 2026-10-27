/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { FileEntry } from '@/services/chat';
import { readWorkspaceText, type WorkspaceTextSnapshot } from '@/services/workspaceText';
import { useWorkspaceDraftStore } from '@/store/useWorkspaceDraftStore';
import { WorkspaceFilePreview } from '../WorkspaceFilePreview';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/components/features/files/FileTypeIcon', () => ({
  FileTypeIcon: () => <span data-testid="file-icon" />,
}));

vi.mock('@/services/chat', () => ({
  getWorkspaceFileContentUrl: (path: string, workspace: string) => `/content?path=${path}&workspace=${workspace}`,
}));

vi.mock('@/services/workspaceText', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/workspaceText')>()),
  readWorkspaceText: vi.fn(),
  saveWorkspaceText: vi.fn(),
  saveWorkspaceTextCopy: vi.fn(),
}));

vi.mock('@/lib/api', () => ({
  getStorageUrl: (url: string) => url,
}));

// The renderers load on demand; here they load for real from the mocks below.
vi.mock('next/dynamic', async () => {
  const react = await import('react');
  return {
    default: (loader: () => Promise<{ default: React.ComponentType<Record<string, unknown>> }>) => {
      const Lazy = react.lazy(loader);
      const Dynamic = (props: Record<string, unknown>) => (
        <react.Suspense fallback={null}>
          <Lazy {...props} />
        </react.Suspense>
      );
      return Dynamic;
    },
  };
});

vi.mock('../../artifacts/renderers/DocumentPreview', () => ({
  default: ({
    content,
    filename,
    resolveUrl,
  }: {
    content: string;
    filename?: string;
    resolveUrl?: (url: string) => string;
  }) => (
    <div data-testid="document-preview" data-filename={filename} data-image={resolveUrl?.('img/a.png')}>
      {content}
    </div>
  ),
}));

vi.mock('../../artifacts/renderers/SpreadsheetPreview', () => ({
  default: ({ content, filename }: { content: string; filename: string }) => (
    <div data-testid="spreadsheet-preview" data-filename={filename}>
      {content}
    </div>
  ),
}));

const WORKSPACE = '/workspace';
const LIMIT = 200 * 1024;

const entry = (name: string): FileEntry => ({
  name,
  path: `${WORKSPACE}/docs/${name}`,
  type: 'file',
  size: 5,
  mtime: null,
  is_text: true,
  children: null,
});

const snapshot = (
  name: string,
  content: string,
  overrides: Partial<WorkspaceTextSnapshot> = {},
): WorkspaceTextSnapshot => ({
  path: `${WORKSPACE}/docs/${name}`,
  name,
  content,
  version: 'v1',
  size: content.length,
  editable: true,
  readonlyReason: null,
  truncated: false,
  ...overrides,
});

const readMock = vi.mocked(readWorkspaceText);

const preview = (file: FileEntry) => <WorkspaceFilePreview file={file} workspace={WORKSPACE} onClose={vi.fn()} />;
const switchButton = (name: 'renderedView' | 'sourceView') => screen.getByRole('button', { name });
const isPressed = (name: 'renderedView' | 'sourceView') => switchButton(name).getAttribute('aria-pressed');
const sourceRows = () => document.querySelector('.numbered-code');

beforeEach(() => {
  vi.clearAllMocks();
  useWorkspaceDraftStore.setState({ drafts: {} });
});

describe('WorkspaceFilePreview of a file that has a rendered view', () => {
  it('opens markdown rendered, with the file name and the saved text', async () => {
    readMock.mockResolvedValue(snapshot('guide.md', '# Title'));

    render(preview(entry('guide.md')));

    const document_ = await screen.findByTestId('document-preview');
    expect(document_.textContent).toBe('# Title');
    expect(document_.getAttribute('data-filename')).toBe('guide.md');
    expect(sourceRows()).toBeNull();
    expect(isPressed('renderedView')).toBe('true');
    expect(isPressed('sourceView')).toBe('false');
  });

  it('opens CSV as a table', async () => {
    readMock.mockResolvedValue(snapshot('data.csv', 'a,b\n1,2'));

    render(preview(entry('data.csv')));

    expect((await screen.findByTestId('spreadsheet-preview')).getAttribute('data-filename')).toBe('data.csv');
  });

  it('shows the source on request and returns to the rendered view', async () => {
    readMock.mockResolvedValue(snapshot('guide.md', '# Title'));
    render(preview(entry('guide.md')));
    await screen.findByTestId('document-preview');

    fireEvent.click(switchButton('sourceView'));

    expect(screen.queryByTestId('document-preview')).toBeNull();
    expect(sourceRows()?.textContent).toContain('# Title');
    expect(isPressed('sourceView')).toBe('true');

    fireEvent.click(switchButton('renderedView'));

    expect(await screen.findByTestId('document-preview')).toBeTruthy();
    expect(sourceRows()).toBeNull();
  });

  it('opens a file of exactly the size limit rendered and a larger one as source', async () => {
    readMock.mockResolvedValueOnce(snapshot('limit.md', 'x', { size: LIMIT }));
    const { unmount } = render(preview(entry('limit.md')));
    expect(await screen.findByTestId('document-preview')).toBeTruthy();
    unmount();

    readMock.mockResolvedValueOnce(snapshot('over.md', 'x', { size: LIMIT + 1 }));
    render(preview(entry('over.md')));
    await waitFor(() => expect(sourceRows()).not.toBeNull());
    expect(screen.queryByTestId('document-preview')).toBeNull();
    expect(isPressed('sourceView')).toBe('true');

    fireEvent.click(switchButton('renderedView'));
    expect(await screen.findByTestId('document-preview')).toBeTruthy();
  });

  it('offers no switch for a file that has no rendered view', async () => {
    readMock.mockResolvedValue(snapshot('notes.txt', 'plain'));

    render(preview(entry('notes.txt')));

    await waitFor(() => expect(sourceRows()).not.toBeNull());
    expect(screen.queryByRole('button', { name: 'renderedView' })).toBeNull();
    expect(screen.queryByRole('group')).toBeNull();
  });

  it('shows only the source of a file that was cut short, since a cut table or document would mislead', async () => {
    readMock.mockResolvedValue(
      snapshot('big.md', 'first part', { truncated: true, editable: false, readonlyReason: 'too_large' }),
    );

    render(preview(entry('big.md')));

    await waitFor(() => expect(sourceRows()).not.toBeNull());
    expect(screen.queryByRole('button', { name: 'renderedView' })).toBeNull();
    expect(screen.queryByTestId('document-preview')).toBeNull();
  });

  it('points a relative image at the content of the file beside the document', async () => {
    readMock.mockResolvedValue(snapshot('guide.md', '![a](img/a.png)'));

    render(preview(entry('guide.md')));

    expect((await screen.findByTestId('document-preview')).getAttribute('data-image')).toBe(
      '/content?path=/workspace/docs/img/a.png&workspace=/workspace',
    );
  });

  it('edits the source, hides the switch meanwhile and comes back to the chosen view', async () => {
    readMock.mockResolvedValue(snapshot('guide.md', '# Title'));
    render(preview(entry('guide.md')));
    await screen.findByTestId('document-preview');

    fireEvent.click(screen.getByTitle('editMode'));

    expect((screen.getByRole('textbox', { hidden: true }) as HTMLTextAreaElement).value).toBe('# Title');
    expect(screen.queryByRole('group')).toBeNull();
    expect(screen.queryByTestId('document-preview')).toBeNull();

    fireEvent.click(screen.getByTitle('viewMode'));

    expect(await screen.findByTestId('document-preview')).toBeTruthy();
    expect(screen.getByRole('group')).toBeTruthy();
  });

  it('lets each file start from its own default, not from the view chosen for the last one', async () => {
    readMock.mockImplementation(async (_workspace, path) => snapshot(path.split('/').pop() ?? '', 'body'));
    const { rerender } = render(preview(entry('one.md')));
    await screen.findByTestId('document-preview');
    fireEvent.click(switchButton('sourceView'));
    expect(screen.queryByTestId('document-preview')).toBeNull();

    rerender(preview(entry('two.md')));

    expect(await screen.findByTestId('document-preview')).toBeTruthy();
    expect(isPressed('renderedView')).toBe('true');
  });
});
