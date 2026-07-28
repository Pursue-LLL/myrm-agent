import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

const mockToast = vi.hoisted(() => ({
  warning: vi.fn(),
  error: vi.fn(),
  success: vi.fn(),
  info: vi.fn(),
}));
vi.mock('@/lib/utils/toast', () => ({ toast: mockToast }));

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, params?: Record<string, unknown>) => {
    if (params) return `${key}:${JSON.stringify(params)}`;
    return key;
  },
}));

const mockUploadFiles = vi.hoisted(() => vi.fn().mockResolvedValue({ uploaded_count: 0, files: [] }));
vi.mock('@/services/file', () => ({ uploadFiles: mockUploadFiles }));

vi.mock('@/services/uploadController', () => ({
  resetUploadController: vi.fn(),
  getUploadSignal: vi.fn(() => new AbortController().signal),
}));

vi.mock('@/lib/utils/fileUtils', () => ({
  computeFileHash: vi.fn(async (f: File) => `hash-${f.name}`),
  isImageFile: vi.fn((ext: string) => ['png', 'jpg', 'jpeg', 'gif', 'webp'].includes(ext)),
  isVideoFile: vi.fn((ext: string) => ['mp4', 'webm', 'mov'].includes(ext)),
  isAudioFile: vi.fn((ext: string) => ['mp3', 'wav', 'ogg'].includes(ext)),
  getFileExtension: vi.fn((name: string) => name.split('.').pop()?.toLowerCase() || ''),
}));

const mockGetModelInfo = vi.hoisted(() =>
  vi.fn().mockReturnValue({ supports_vision: true, supports_video_input: true }),
);
vi.mock('@/store/useProviderStore', () => ({
  default: {
    getState: () => ({
      defaultModelConfig: {
        baseModel: { primary: { providerId: 'p1', model: 'm1' } },
        visionFallbackModel: null,
      },
      getModelInfo: mockGetModelInfo,
    }),
  },
}));

import { useInputFileUpload } from '../message-input/useInputFileUpload';

type UploadParams = Parameters<typeof useInputFileUpload>[0];

function createClipboardEvent(files: File[]): React.ClipboardEvent {
  const items: DataTransferItem[] = files.map((file) => ({
    kind: 'file' as const,
    type: file.type,
    getAsFile: () => file,
    getAsString: vi.fn(),
    webkitGetAsEntry: vi.fn(),
  }));
  return {
    clipboardData: {
      items: items as unknown as DataTransferItemList,
      getData: vi.fn(),
      setData: vi.fn(),
      clearData: vi.fn(),
      types: [],
      files: [] as unknown as FileList,
      dropEffect: 'none' as const,
      effectAllowed: 'none' as const,
      setDragImage: vi.fn(),
    },
    preventDefault: vi.fn(),
    stopPropagation: vi.fn(),
  } as unknown as React.ClipboardEvent;
}

function createClipboardEventWithTextOnly(): React.ClipboardEvent {
  const items: DataTransferItem[] = [
    {
      kind: 'string' as const,
      type: 'text/plain',
      getAsFile: () => null,
      getAsString: vi.fn(),
      webkitGetAsEntry: vi.fn(),
    },
  ];
  return {
    clipboardData: {
      items: items as unknown as DataTransferItemList,
      getData: vi.fn(() => 'plain text'),
      setData: vi.fn(),
      clearData: vi.fn(),
      types: ['text/plain'],
      files: [] as unknown as FileList,
      dropEffect: 'none' as const,
      effectAllowed: 'none' as const,
      setDragImage: vi.fn(),
    },
    preventDefault: vi.fn(),
    stopPropagation: vi.fn(),
  } as unknown as React.ClipboardEvent;
}

describe('useInputFileUpload', () => {
  const defaultParams: UploadParams = {
    actionMode: 'normal' as const,
    files: [],
    setFiles: vi.fn<(files: UploadParams['files']) => void>(),
    setHideAttachList: vi.fn<(hide: boolean) => void>(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockUploadFiles.mockResolvedValue({ uploaded_count: 0, files: [] });
  });

  describe('handlePaste - core behavior', () => {
    it('should extract all file types from clipboard (not just images)', async () => {
      mockUploadFiles.mockResolvedValue({
        uploaded_count: 2,
        files: [
          { fileName: 'doc.pdf', fileUrl: '/f/doc.pdf' },
          { fileName: 'img.png', fileUrl: '/f/img.png' },
        ],
      });

      const { result } = renderHook(() => useInputFileUpload(defaultParams));

      const pdf = new File(['pdf content'], 'doc.pdf', { type: 'application/pdf' });
      const img = new File(['img content'], 'img.png', { type: 'image/png' });
      const event = createClipboardEvent([pdf, img]);

      await act(async () => {
        await result.current.handlePaste(event);
      });

      expect(event.preventDefault).toHaveBeenCalled();
      expect(mockUploadFiles).toHaveBeenCalledWith([pdf, img], expect.anything());
    });

    it('should handle pasting a single non-image file (PDF)', async () => {
      mockUploadFiles.mockResolvedValue({
        uploaded_count: 1,
        files: [{ fileName: 'report.pdf', fileUrl: '/f/report.pdf' }],
      });

      const { result } = renderHook(() => useInputFileUpload(defaultParams));
      const pdf = new File(['pdf'], 'report.pdf', { type: 'application/pdf' });
      const event = createClipboardEvent([pdf]);

      await act(async () => {
        await result.current.handlePaste(event);
      });

      expect(event.preventDefault).toHaveBeenCalled();
      expect(mockUploadFiles).toHaveBeenCalledWith([pdf], expect.anything());
    });

    it('should not preventDefault when clipboard has only text (no files)', async () => {
      const { result } = renderHook(() => useInputFileUpload(defaultParams));
      const event = createClipboardEventWithTextOnly();

      await act(async () => {
        await result.current.handlePaste(event);
      });

      expect(event.preventDefault).not.toHaveBeenCalled();
      expect(mockUploadFiles).not.toHaveBeenCalled();
    });

    it('should skip paste handling in fast mode', async () => {
      const { result } = renderHook(() => useInputFileUpload({ ...defaultParams, actionMode: 'fast' }));

      const img = new File(['img'], 'test.png', { type: 'image/png' });
      const event = createClipboardEvent([img]);

      await act(async () => {
        await result.current.handlePaste(event);
      });

      expect(event.preventDefault).not.toHaveBeenCalled();
      expect(mockUploadFiles).not.toHaveBeenCalled();
    });

    it('should handle empty clipboardData gracefully', async () => {
      const { result } = renderHook(() => useInputFileUpload(defaultParams));

      const event = {
        clipboardData: null,
        preventDefault: vi.fn(),
      } as unknown as React.ClipboardEvent;

      await act(async () => {
        await result.current.handlePaste(event);
      });

      expect(event.preventDefault).not.toHaveBeenCalled();
      expect(mockUploadFiles).not.toHaveBeenCalled();
    });

    it('should handle getAsFile returning null gracefully', async () => {
      const { result } = renderHook(() => useInputFileUpload(defaultParams));

      const items: DataTransferItem[] = [
        {
          kind: 'file' as const,
          type: 'application/pdf',
          getAsFile: () => null,
          getAsString: vi.fn(),
          webkitGetAsEntry: vi.fn(),
        },
      ];
      const event = {
        clipboardData: {
          items: items as unknown as DataTransferItemList,
        },
        preventDefault: vi.fn(),
      } as unknown as React.ClipboardEvent;

      await act(async () => {
        await result.current.handlePaste(event);
      });

      expect(event.preventDefault).not.toHaveBeenCalled();
      expect(mockUploadFiles).not.toHaveBeenCalled();
    });
  });

  describe('handlePaste - delegates to handleDroppedFiles logic', () => {
    it('should show vision warning when pasting image with non-vision model', async () => {
      mockGetModelInfo.mockReturnValue({ supports_vision: false, supports_video_input: false });
      mockUploadFiles.mockResolvedValue({
        uploaded_count: 1,
        files: [{ fileName: 'img.png', fileUrl: '/f/img.png' }],
      });

      const { result } = renderHook(() => useInputFileUpload(defaultParams));
      const img = new File(['img'], 'img.png', { type: 'image/png' });
      const event = createClipboardEvent([img]);

      await act(async () => {
        await result.current.handlePaste(event);
      });

      expect(mockToast.warning).toHaveBeenCalledWith('modelNotSupportVision');
    });

    it('should reject oversized files when pasted', async () => {
      const { result } = renderHook(() => useInputFileUpload(defaultParams));
      const bigFile = new File([new ArrayBuffer(51 * 1024 * 1024)], 'big.zip', {
        type: 'application/zip',
      });
      Object.defineProperty(bigFile, 'size', { value: 51 * 1024 * 1024 });
      const event = createClipboardEvent([bigFile]);

      await act(async () => {
        await result.current.handlePaste(event);
      });

      expect(mockToast.error).toHaveBeenCalled();
      expect(mockUploadFiles).not.toHaveBeenCalled();
    });
  });

  describe('handleDroppedFiles - file type validation', () => {
    it('should reject video exceeding 100MB limit', async () => {
      const { result } = renderHook(() => useInputFileUpload(defaultParams));
      const bigVideo = new File([], 'huge.mp4', { type: 'video/mp4' });
      Object.defineProperty(bigVideo, 'size', { value: 101 * 1024 * 1024 });

      await act(async () => {
        await result.current.handleDroppedFiles([bigVideo]);
      });

      expect(mockToast.error).toHaveBeenCalledWith('videoTooLarge', expect.anything());
      expect(mockUploadFiles).not.toHaveBeenCalled();
    });

    it('should reject audio exceeding 25MB limit', async () => {
      const { result } = renderHook(() => useInputFileUpload(defaultParams));
      const bigAudio = new File([], 'huge.mp3', { type: 'audio/mpeg' });
      Object.defineProperty(bigAudio, 'size', { value: 26 * 1024 * 1024 });

      await act(async () => {
        await result.current.handleDroppedFiles([bigAudio]);
      });

      expect(mockToast.error).toHaveBeenCalledWith('audioTooLarge', expect.anything());
      expect(mockUploadFiles).not.toHaveBeenCalled();
    });

    it('should accept files within size limits', async () => {
      mockUploadFiles.mockResolvedValue({
        uploaded_count: 1,
        files: [{ fileName: 'small.pdf', fileUrl: '/f/small.pdf' }],
      });

      const { result } = renderHook(() => useInputFileUpload(defaultParams));
      const smallPdf = new File(['content'], 'small.pdf', { type: 'application/pdf' });
      Object.defineProperty(smallPdf, 'size', { value: 1024 });

      await act(async () => {
        await result.current.handleDroppedFiles([smallPdf]);
      });

      expect(mockUploadFiles).toHaveBeenCalledWith([smallPdf], expect.anything());
    });
  });

  describe('uploadInputFiles - deduplication', () => {
    it('should deduplicate files by SHA-256 hash', async () => {
      const existingFiles = [
        {
          fileName: 'a.pdf',
          fileUrl: '/f/a.pdf',
          fileType: 'uploaded' as const,
          fileExtension: 'pdf',
          contentHash: 'hash-a.pdf',
        },
      ];
      mockUploadFiles.mockResolvedValue({
        uploaded_count: 1,
        files: [{ fileName: 'b.pdf', fileUrl: '/f/b.pdf' }],
      });

      const { result } = renderHook(() => useInputFileUpload({ ...defaultParams, files: existingFiles }));

      const dupeFile = new File(['a'], 'a.pdf', { type: 'application/pdf' });
      const newFile = new File(['b'], 'b.pdf', { type: 'application/pdf' });

      await act(async () => {
        await result.current.handleDroppedFiles([dupeFile, newFile]);
      });

      expect(mockUploadFiles).toHaveBeenCalledWith([newFile], expect.anything());
    });

    it('should show info toast when all files are duplicates', async () => {
      const existingFiles = [
        {
          fileName: 'a.pdf',
          fileUrl: '/f/a.pdf',
          fileType: 'uploaded' as const,
          fileExtension: 'pdf',
          contentHash: 'hash-a.pdf',
        },
      ];

      const { result } = renderHook(() => useInputFileUpload({ ...defaultParams, files: existingFiles }));

      const dupeFile = new File(['a'], 'a.pdf', { type: 'application/pdf' });

      await act(async () => {
        await result.current.handleDroppedFiles([dupeFile]);
      });

      expect(mockToast.info).toHaveBeenCalledWith('duplicateFiles');
      expect(mockUploadFiles).not.toHaveBeenCalled();
    });
  });

  describe('isUploadingPaste state', () => {
    it('should set isUploadingPaste during upload and reset after', async () => {
      mockUploadFiles.mockResolvedValue({ uploaded_count: 0, files: [] });

      const { result } = renderHook(() => useInputFileUpload(defaultParams));
      expect(result.current.isUploadingPaste).toBe(false);

      const file = new File(['x'], 'x.txt', { type: 'text/plain' });

      await act(async () => {
        await result.current.handleDroppedFiles([file]);
      });

      expect(result.current.isUploadingPaste).toBe(false);
    });

    it('should reset isUploadingPaste even on upload error', async () => {
      mockUploadFiles.mockRejectedValue(new Error('network error'));

      const { result } = renderHook(() => useInputFileUpload(defaultParams));
      const file = new File(['x'], 'x.txt', { type: 'text/plain' });

      await act(async () => {
        await result.current.handleDroppedFiles([file]);
      });

      expect(result.current.isUploadingPaste).toBe(false);
      expect(mockToast.error).toHaveBeenCalledWith('uploadError');
    });

    it('should silently handle AbortError (user cancelled)', async () => {
      const abortError = new DOMException('aborted', 'AbortError');
      mockUploadFiles.mockRejectedValue(abortError);

      const { result } = renderHook(() => useInputFileUpload(defaultParams));
      const file = new File(['x'], 'x.txt', { type: 'text/plain' });

      await act(async () => {
        await result.current.handleDroppedFiles([file]);
      });

      expect(result.current.isUploadingPaste).toBe(false);
      expect(mockToast.error).not.toHaveBeenCalled();
    });
  });
});
