import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useResizableSidebar } from '../useResizableSidebar';

describe('useResizableSidebar', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    document.body.style.userSelect = '';
    document.body.style.cursor = '';
  });

  afterEach(() => {
    localStorage.clear();
  });

  describe('initialization', () => {
    it('should initialize with default width of 280', () => {
      const { result } = renderHook(() => useResizableSidebar());
      expect(result.current.width).toBe(280);
      expect(result.current.isDragging).toBe(false);
    });

    it('should restore width from localStorage', () => {
      localStorage.setItem('myrm-sidebar-width', '350');
      const { result } = renderHook(() => useResizableSidebar());
      expect(result.current.width).toBe(350);
    });

    it('should ignore invalid localStorage values below minimum', () => {
      localStorage.setItem('myrm-sidebar-width', '100');
      const { result } = renderHook(() => useResizableSidebar());
      expect(result.current.width).toBe(280);
    });

    it('should ignore invalid localStorage values above maximum', () => {
      localStorage.setItem('myrm-sidebar-width', '999');
      const { result } = renderHook(() => useResizableSidebar());
      expect(result.current.width).toBe(280);
    });

    it('should ignore non-numeric localStorage values', () => {
      localStorage.setItem('myrm-sidebar-width', 'invalid');
      const { result } = renderHook(() => useResizableSidebar());
      expect(result.current.width).toBe(280);
    });
  });

  describe('drag interaction', () => {
    it('should set isDragging to true on mouseDown', () => {
      const { result } = renderHook(() => useResizableSidebar());

      act(() => {
        result.current.handleMouseDown({
          clientX: 300,
          preventDefault: vi.fn(),
          stopPropagation: vi.fn(),
        } as unknown as React.MouseEvent);
      });

      expect(result.current.isDragging).toBe(true);
      expect(document.body.style.userSelect).toBe('none');
      expect(document.body.style.cursor).toBe('col-resize');
    });

    it('should register mousemove/mouseup listeners when dragging', () => {
      const addEventListenerSpy = vi.spyOn(window, 'addEventListener');
      const { result } = renderHook(() => useResizableSidebar());

      act(() => {
        result.current.handleMouseDown({
          clientX: 300,
          preventDefault: vi.fn(),
          stopPropagation: vi.fn(),
        } as unknown as React.MouseEvent);
      });

      expect(addEventListenerSpy).toHaveBeenCalledWith('mousemove', expect.any(Function));
      expect(addEventListenerSpy).toHaveBeenCalledWith('mouseup', expect.any(Function));

      addEventListenerSpy.mockRestore();
    });

    it('should clamp width to min/max bounds on mouseUp', () => {
      const { result } = renderHook(() => useResizableSidebar());

      act(() => {
        result.current.handleMouseDown({
          clientX: 300,
          preventDefault: vi.fn(),
          stopPropagation: vi.fn(),
        } as unknown as React.MouseEvent);
      });

      // Simulate drag far to the right (beyond max)
      act(() => {
        const upEvent = new MouseEvent('mouseup', { clientX: 900 });
        window.dispatchEvent(upEvent);
      });

      expect(result.current.isDragging).toBe(false);
      expect(result.current.width).toBe(450); // MAX_WIDTH
      expect(document.body.style.userSelect).toBe('');
      expect(document.body.style.cursor).toBe('');
    });

    it('should persist width on valid mouseUp', () => {
      const { result } = renderHook(() => useResizableSidebar());

      act(() => {
        result.current.handleMouseDown({
          clientX: 300,
          preventDefault: vi.fn(),
          stopPropagation: vi.fn(),
        } as unknown as React.MouseEvent);
      });

      act(() => {
        const upEvent = new MouseEvent('mouseup', { clientX: 330 });
        window.dispatchEvent(upEvent);
      });

      expect(localStorage.getItem('myrm-sidebar-width')).toBe('310');
    });
  });

  describe('auto-collapse', () => {
    it('should call onCollapse when dragged below threshold', () => {
      const onCollapse = vi.fn();
      const { result } = renderHook(() => useResizableSidebar({ onCollapse }));

      act(() => {
        result.current.handleMouseDown({
          clientX: 300,
          preventDefault: vi.fn(),
          stopPropagation: vi.fn(),
        } as unknown as React.MouseEvent);
      });

      // Drag far to the left (below collapse threshold)
      act(() => {
        const upEvent = new MouseEvent('mouseup', { clientX: 100 });
        window.dispatchEvent(upEvent);
      });

      expect(onCollapse).toHaveBeenCalledTimes(1);
      // Width should be restored to original (280)
      expect(result.current.width).toBe(280);
    });

    it('should not persist width on collapse', () => {
      const onCollapse = vi.fn();
      const { result } = renderHook(() => useResizableSidebar({ onCollapse }));

      act(() => {
        result.current.handleMouseDown({
          clientX: 300,
          preventDefault: vi.fn(),
          stopPropagation: vi.fn(),
        } as unknown as React.MouseEvent);
      });

      act(() => {
        const upEvent = new MouseEvent('mouseup', { clientX: 100 });
        window.dispatchEvent(upEvent);
      });

      expect(localStorage.getItem('myrm-sidebar-width')).toBeNull();
    });
  });

  describe('double-click reset', () => {
    it('should reset to default width on double click', () => {
      localStorage.setItem('myrm-sidebar-width', '400');
      const { result } = renderHook(() => useResizableSidebar());

      // After init, width is 400
      expect(result.current.width).toBe(400);

      act(() => {
        result.current.handleDoubleClick();
      });

      expect(result.current.width).toBe(280);
      expect(localStorage.getItem('myrm-sidebar-width')).toBe('280');
    });
  });

  describe('cleanup', () => {
    it('should remove event listeners on unmount', () => {
      const removeEventListenerSpy = vi.spyOn(window, 'removeEventListener');
      const { result, unmount } = renderHook(() => useResizableSidebar());

      act(() => {
        result.current.handleMouseDown({
          clientX: 300,
          preventDefault: vi.fn(),
          stopPropagation: vi.fn(),
        } as unknown as React.MouseEvent);
      });

      unmount();

      expect(removeEventListenerSpy).toHaveBeenCalledWith('mousemove', expect.any(Function));
      expect(removeEventListenerSpy).toHaveBeenCalledWith('mouseup', expect.any(Function));

      removeEventListenerSpy.mockRestore();
    });
  });
});
