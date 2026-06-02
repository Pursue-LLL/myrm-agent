import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useDragDrop } from '../useDragDrop';

// Mock sonner toast
vi.mock('sonner', () => ({
  toast: {
    error: vi.fn(),
  },
}));

// Mock next-intl
vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, params?: Record<string, unknown>) => {
    if (key === 'tooManyFiles') return `Too many files, maximum ${params?.max} files allowed`;
    if (key === 'invalidFileType') return `Unsupported file type: ${params?.types}`;
    return key;
  },
}));

describe('useDragDrop', () => {
  const mockOnFilesSelected = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  const createDragEvent = (
    type: string,
    files: File[] = [],
    dataTransferTypes: string[] = ['Files'],
  ): React.DragEvent => {
    const event = {
      type,
      preventDefault: vi.fn(),
      stopPropagation: vi.fn(),
      dataTransfer: {
        types: dataTransferTypes,
        dropEffect: 'none' as DataTransfer['dropEffect'],
        items: files.map((file) => ({
          kind: 'file' as const,
          type: file.type,
          getAsFile: () => file,
        })),
      },
      clientX: 100,
      clientY: 100,
    } as unknown as React.DragEvent;
    return event;
  };

  describe('P0 Bug Fix: dragenter/dragleave Counter', () => {
    it('should not flicker isDragging when dragging over nested elements', () => {
      const { result } = renderHook(() =>
        useDragDrop({
          onFilesSelected: mockOnFilesSelected,
        }),
      );

      // Initial state
      expect(result.current.isDragging).toBe(false);

      // Drag enter parent
      act(() => {
        const event = createDragEvent('dragenter');
        result.current.dragHandlers.onDragEnter(event);
      });
      expect(result.current.isDragging).toBe(true);

      // Drag enter child (counter should increment)
      act(() => {
        const event = createDragEvent('dragenter');
        result.current.dragHandlers.onDragEnter(event);
      });
      expect(result.current.isDragging).toBe(true); // Still true

      // Drag leave child (counter should decrement but not reset)
      act(() => {
        const event = createDragEvent('dragleave');
        result.current.dragHandlers.onDragLeave(event);
      });
      expect(result.current.isDragging).toBe(true); // Still true (P0 fix!)

      // Drag leave parent (counter should reset)
      act(() => {
        const event = createDragEvent('dragleave');
        result.current.dragHandlers.onDragLeave(event);
      });
      expect(result.current.isDragging).toBe(false);
    });
  });

  describe('P1 Optimization: Boundary Detection', () => {
    it('should reset isDragging when dragging outside window bounds', () => {
      const { result } = renderHook(() =>
        useDragDrop({
          onFilesSelected: mockOnFilesSelected,
        }),
      );

      // Drag enter
      act(() => {
        const event = createDragEvent('dragenter');
        result.current.dragHandlers.onDragEnter(event);
      });
      expect(result.current.isDragging).toBe(true);

      // Drag leave to outside window bounds (clientX <= 0)
      act(() => {
        const event = {
          ...createDragEvent('dragleave'),
          clientX: 0,
          clientY: 100,
        };
        result.current.dragHandlers.onDragLeave(event);
      });
      expect(result.current.isDragging).toBe(false); // P1 fix!
    });
  });

  describe('P2 Optimization: Drag Source Detection', () => {
    it('should only respond to file drag (not text/link)', () => {
      const { result } = renderHook(() =>
        useDragDrop({
          onFilesSelected: mockOnFilesSelected,
        }),
      );

      // Drag text (no "Files" in types)
      act(() => {
        const event = createDragEvent('dragenter', [], ['text/plain']);
        result.current.dragHandlers.onDragEnter(event);
      });
      expect(result.current.isDragging).toBe(false); // P2 fix!

      // Drag file (has "Files" in types)
      act(() => {
        const event = createDragEvent('dragenter', [], ['Files']);
        result.current.dragHandlers.onDragEnter(event);
      });
      expect(result.current.isDragging).toBe(true);
    });
  });

  describe('File Type Validation', () => {
    it('should accept files matching accept pattern', () => {
      const { result } = renderHook(() =>
        useDragDrop({
          onFilesSelected: mockOnFilesSelected,
          accept: ['image/*'],
        }),
      );

      const imageFile = new File([''], 'test.png', { type: 'image/png' });

      act(() => {
        const event = createDragEvent('drop', [imageFile]);
        result.current.dragHandlers.onDrop(event);
      });

      expect(mockOnFilesSelected).toHaveBeenCalledWith([imageFile]);
    });

    it('should reject files not matching accept pattern', async () => {
      const { toast } = await import('sonner');
      const { result } = renderHook(() =>
        useDragDrop({
          onFilesSelected: mockOnFilesSelected,
          accept: ['image/*'],
        }),
      );

      const pdfFile = new File([''], 'test.pdf', { type: 'application/pdf' });

      act(() => {
        const event = createDragEvent('drop', [pdfFile]);
        result.current.dragHandlers.onDrop(event);
      });

      expect(mockOnFilesSelected).not.toHaveBeenCalled();
      expect(toast.error).toHaveBeenCalledWith(expect.stringContaining('Unsupported file type'));
    });
  });

  describe('Max Files Limit', () => {
    it('should reject files exceeding maxFiles limit', async () => {
      const { toast } = await import('sonner');
      const { result } = renderHook(() =>
        useDragDrop({
          onFilesSelected: mockOnFilesSelected,
          maxFiles: 2,
        }),
      );

      const files = [
        new File([''], 'test1.png', { type: 'image/png' }),
        new File([''], 'test2.png', { type: 'image/png' }),
        new File([''], 'test3.png', { type: 'image/png' }),
      ];

      act(() => {
        const event = createDragEvent('drop', files);
        result.current.dragHandlers.onDrop(event);
      });

      expect(mockOnFilesSelected).not.toHaveBeenCalled();
      expect(toast.error).toHaveBeenCalledWith(expect.stringContaining('Too many files'));
    });
  });

  describe('Disabled State', () => {
    it('should not respond to drag events when disabled', () => {
      const { result } = renderHook(() =>
        useDragDrop({
          onFilesSelected: mockOnFilesSelected,
          disabled: true,
        }),
      );

      act(() => {
        const event = createDragEvent('dragenter');
        result.current.dragHandlers.onDragEnter(event);
      });

      expect(result.current.isDragging).toBe(false);
    });
  });

  describe('Drop Handler', () => {
    it('should reset drag state on drop', () => {
      const { result } = renderHook(() =>
        useDragDrop({
          onFilesSelected: mockOnFilesSelected,
        }),
      );

      // Drag enter
      act(() => {
        const event = createDragEvent('dragenter');
        result.current.dragHandlers.onDragEnter(event);
      });
      expect(result.current.isDragging).toBe(true);

      // Drop
      const file = new File([''], 'test.png', { type: 'image/png' });
      act(() => {
        const event = createDragEvent('drop', [file]);
        result.current.dragHandlers.onDrop(event);
      });

      expect(result.current.isDragging).toBe(false);
      expect(mockOnFilesSelected).toHaveBeenCalledWith([file]);
    });
  });
});
