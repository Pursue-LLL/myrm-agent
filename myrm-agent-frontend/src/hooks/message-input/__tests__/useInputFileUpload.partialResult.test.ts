import { act, renderHook } from '@testing-library/react';
import type React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useInputFileUpload } from '@/hooks/message-input/useInputFileUpload';
import type { File as ChatFile } from '@/store/chat/types';

const mockToast = vi.hoisted(() => ({ warning: vi.fn(), error: vi.fn(), success: vi.fn(), info: vi.fn() }));
const mockUpload = vi.hoisted(() => vi.fn());

vi.mock('@/lib/utils/toast', () => ({ toast: mockToast }));
vi.mock('@/services/file', () => ({ uploadFilesWithProgress: mockUpload }));
vi.mock('@/services/incognitoUploadOptions', () => ({ incognitoUploadOptions: () => ({}) }));
vi.mock('@/services/uploadController', () => ({
  resetUploadController: vi.fn(),
  getUploadSignal: () => new AbortController().signal,
}));
vi.mock('@/lib/utils/imageAdmission', () => ({ admitAndCompressFiles: async (files: File[]) => files }));
vi.mock('@/lib/utils/fileUtils', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/utils/fileUtils')>()),
  computeFileHash: async (file: File) => `hash-${file.name}-${file.size}`,
}));
vi.mock('@/store/useProviderStore', () => ({ default: { getState: () => ({}) } }));
vi.mock('@/store/config/visionCapability', () => ({
  hasConfiguredVisionCapability: vi.fn(() => false),
  hasVisionFallbackForVideo: vi.fn(() => false),
}));
vi.mock('@/store/config/visionConfigGap', () => ({ showVisionNotConfiguredToast: vi.fn() }));

const LARGE_DOC_BYTES = 101 * 1024;

const stored = (fileName: string, fileId: string) => ({ fileId, fileName, fileUrl: `/files/${fileId}` });

/** Drives the hook with a file list that applies state updaters the way React would. */
function setup() {
  let staged: ChatFile[] = [];
  const setFiles = vi.fn((next: React.SetStateAction<ChatFile[]>) => {
    staged = typeof next === 'function' ? next(staged) : next;
  });
  const { result } = renderHook(() =>
    useInputFileUpload({ actionMode: 'agent', files: [], setFiles, setHideAttachList: vi.fn() }),
  );
  return {
    upload: (files: File[]) =>
      act(async () => {
        await result.current.uploadInputFiles(files);
      }),
    chips: () => staged.map(({ fileName, id, status }) => ({ fileName, id, status })),
  };
}

describe('useInputFileUpload when the server keeps only some of the files', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('gives each file the id the server stored for it and fails the one it left out', async () => {
    mockUpload.mockResolvedValue({
      uploaded_count: 2,
      files: [stored('notes.pdf', 'id-notes'), stored('report.docx', 'id-report')],
    });
    const { upload, chips } = setup();

    await upload([new File(['n'], 'notes.pdf'), new File(['t'], 'tool.exe'), new File(['r'], 'report.docx')]);

    expect(chips()).toEqual([
      { fileName: 'notes.pdf', id: 'id-notes', status: 'ready' },
      { fileName: 'tool.exe', id: expect.stringMatching(/^temp_/), status: 'error' },
      { fileName: 'report.docx', id: 'id-report', status: 'ready' },
    ]);
    expect(mockToast.error).toHaveBeenCalledWith('uploadPartialFailed');
  });

  it('hands same-named files their ids in the order they were sent', async () => {
    mockUpload.mockResolvedValue({
      uploaded_count: 2,
      files: [stored('scan.pdf', 'id-first'), stored('scan.pdf', 'id-second')],
    });
    const { upload, chips } = setup();

    await upload([
      new File(['1'], 'scan.pdf'),
      new File(['2-longer'], 'bad.exe'),
      new File(['3-longest-one'], 'scan.pdf'),
    ]);

    expect(chips().map(({ id, status }) => ({ id, status }))).toEqual([
      { id: 'id-first', status: 'ready' },
      { id: expect.stringMatching(/^temp_/), status: 'error' },
      { id: 'id-second', status: 'ready' },
    ]);
  });

  it('pairs by position when the server kept every file, even if it spelled a name differently', async () => {
    mockUpload.mockResolvedValue({
      uploaded_count: 2,
      files: [stored('report.pdf', 'id-a'), stored('notes.txt', 'id-b')],
    });
    const { upload, chips } = setup();

    await upload([new File(['a'], 'Report.PDF'), new File(['b'], 'Notes.txt')]);

    expect(chips().map(({ id, status }) => ({ id, status }))).toEqual([
      { id: 'id-a', status: 'ready' },
      { id: 'id-b', status: 'ready' },
    ]);
    expect(mockToast.error).not.toHaveBeenCalled();
    expect(mockToast.success).toHaveBeenCalledTimes(1);
  });

  it('raises no notice for a large document the server left out', async () => {
    mockUpload.mockResolvedValue({ uploaded_count: 1, files: [stored('notes.txt', 'id-notes')] });
    const { upload } = setup();

    await upload([new File(['n'], 'notes.txt'), new File([new Uint8Array(LARGE_DOC_BYTES)], 'manual.docx')]);

    expect(mockToast.info).not.toHaveBeenCalled();
  });

  it('says nothing about indexing when a large document goes up: the model reads the document itself', async () => {
    mockUpload.mockResolvedValue({ uploaded_count: 1, files: [stored('manual.docx', 'id-manual')] });
    const { upload, chips } = setup();

    await upload([new File([new Uint8Array(LARGE_DOC_BYTES)], 'manual.docx')]);

    expect(chips()).toEqual([{ fileName: 'manual.docx', id: 'id-manual', status: 'ready' }]);
    expect(mockToast.success).toHaveBeenCalledTimes(1);
    expect(mockToast.info).not.toHaveBeenCalled();
  });
});
