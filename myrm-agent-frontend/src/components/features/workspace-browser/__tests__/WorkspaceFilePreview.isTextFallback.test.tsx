import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { FileEntry } from '@/services/chat';

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const stableT = (key: string) => key;

vi.mock('sonner', () => {
  const toastFn = Object.assign(vi.fn(), {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
    promise: vi.fn(),
    loading: vi.fn(),
    dismiss: vi.fn(),
    message: vi.fn(),
  });
  return { __esModule: true, default: toastFn, toast: toastFn };
});

vi.mock('@/components/features/cli-visualization/CLIFileIcon', () => ({
  CLIFileIcon: () => <div data-testid="file-icon" />,
}));

vi.mock('@/services/chat', () => ({
  fetchWorkspaceFileContent: vi.fn().mockResolvedValue('file content'),
  getWorkspaceFileContentUrl: vi.fn(
    (path: string, _workspace: string, _download?: boolean) => `/api/v1/files/browse/content?path=${encodeURIComponent(path)}`,
  ),
  saveWorkspaceFileContent: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('@/lib/api', () => ({
  getStorageUrl: (url: string) => url,
}));

vi.mock('next/dynamic', () => ({
  __esModule: true,
  default: (loader: () => Promise<unknown>) => {
    const DynamicComponent = (props: Record<string, unknown>) => {
      const Comp = null as unknown as React.ComponentType<Record<string, unknown>>;
      void loader;
      return Comp ? <Comp {...props} /> : null;
    };
    return DynamicComponent;
  },
}));

vi.mock('@/components/features/artifacts/renderers/MediaPreview', () => ({
  SvgPreview: () => <div data-testid="svg" />,
  ImagePreview: () => <div data-testid="image" />,
  VideoPreview: () => <div data-testid="video" />,
  AudioPreview: () => <div data-testid="audio" />,
}));
vi.mock('@/components/features/artifacts/PdfPreview', () => ({ default: () => <div data-testid="pdf" /> }));
vi.mock('@/components/features/artifacts/renderers/DocxPreview', () => ({ default: () => <div data-testid="docx" /> }));
vi.mock('@/components/features/artifacts/renderers/PptxPreview', () => ({ default: () => <div data-testid="pptx" /> }));
vi.mock('@/components/features/artifacts/renderers/SpreadsheetPreview', () => ({ default: () => <div data-testid="xlsx" /> }));

import { fetchWorkspaceFileContent } from '@/services/chat';
import { WorkspaceFilePreview } from '../WorkspaceFilePreview';

const binaryFile: FileEntry = {
  name: 'artifact.dat',
  path: '/workspace/artifact.dat',
  type: 'file',
  size: 1024,
  mtime: '2026-08-13T00:00:00+00:00',
  is_text: false,
  children: null,
};

const unknownTextFile: FileEntry = {
  name: 'config.xyz',
  path: '/workspace/config.xyz',
  type: 'file',
  size: 32,
  mtime: '2026-08-13T00:00:00+00:00',
  is_text: true,
  children: null,
};

const renderPreview = (file: FileEntry) =>
  render(<WorkspaceFilePreview file={file} workspace="/workspace" onClose={vi.fn()} />);

describe('WorkspaceFilePreview unknown-extension fallback', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('routes unknown binary files to the unsupported download fallback without fetching text', async () => {
    renderPreview(binaryFile);
    expect(await screen.findByTestId('workspace-preview-unsupported')).toBeTruthy();
    expect(fetchWorkspaceFileContent).not.toHaveBeenCalled();
  });

  it('renders unknown text files as plain text content', async () => {
    renderPreview(unknownTextFile);
    expect(await screen.findByText('file content')).toBeTruthy();
    expect(fetchWorkspaceFileContent).toHaveBeenCalledWith('/workspace/config.xyz', '/workspace');
  });
});
