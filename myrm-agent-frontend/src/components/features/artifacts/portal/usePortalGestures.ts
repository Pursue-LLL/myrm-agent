import { useCallback, useRef, useState, useEffect } from 'react';
import { SWIPE_CLOSE_THRESHOLD, SWIPE_MAX_OFFSET } from '@/lib/constants/artifact';

const MIN_PANEL_WIDTH = 320;
const MAX_PANEL_WIDTH = 1200;
const KEYBOARD_STEP = 20;

interface UsePortalGesturesProps {
  isMobile: boolean;
  panelWidth: number;
  onClose: () => void;
  onSetPanelWidth: (width: number) => void;
}

/** 左缘分隔条的 ARIA 语义与指针、键盘操作；调用方自行补 `aria-label` 与样式。 */
interface PortalSeparatorProps {
  role: 'separator';
  tabIndex: 0;
  'aria-orientation': 'vertical';
  'aria-valuenow': number;
  'aria-valuemin': number;
  'aria-valuemax': number;
  onMouseDown: (e: React.MouseEvent) => void;
  onKeyDown: (e: React.KeyboardEvent) => void;
}

interface PortalGesturesReturn {
  // 触摸滑动
  swipeOffset: number;
  isSwiping: boolean;
  handleTouchStart: (e: React.TouchEvent) => void;
  handleTouchMove: (e: React.TouchEvent) => void;
  handleTouchEnd: () => void;
  // 拖拽调整宽度
  isDragging: boolean;
  separatorProps: PortalSeparatorProps;
}

/** Portal 手势逻辑 Hook */
export function usePortalGestures({
  isMobile,
  panelWidth,
  onClose,
  onSetPanelWidth,
}: UsePortalGesturesProps): PortalGesturesReturn {
  // 触摸手势状态
  const touchStartY = useRef(0);
  const touchCurrentY = useRef(0);
  const [swipeOffset, setSwipeOffset] = useState(0);
  const [isSwiping, setIsSwiping] = useState(false);

  // 拖拽调整宽度状态
  const [isDragging, setIsDragging] = useState(false);
  const dragStartX = useRef(0);
  const dragStartWidth = useRef(0);
  const rafRef = useRef<number | null>(null);

  // 触摸开始
  const handleTouchStart = useCallback(
    (e: React.TouchEvent) => {
      if (!isMobile) {
        return;
      }
      touchStartY.current = e.touches[0].clientY;
      touchCurrentY.current = e.touches[0].clientY;
      setIsSwiping(true);
    },
    [isMobile],
  );

  // 触摸移动
  const handleTouchMove = useCallback(
    (e: React.TouchEvent) => {
      if (!isMobile || !isSwiping) {
        return;
      }
      touchCurrentY.current = e.touches[0].clientY;
      const delta = touchCurrentY.current - touchStartY.current;
      // 只允许向下滑动
      if (delta > 0) {
        setSwipeOffset(Math.min(delta, SWIPE_MAX_OFFSET));
      }
    },
    [isMobile, isSwiping],
  );

  // 触摸结束
  const handleTouchEnd = useCallback(() => {
    if (!isMobile || !isSwiping) {
      return;
    }
    setIsSwiping(false);

    // 如果下滑超过阈值，关闭 Portal
    if (swipeOffset > SWIPE_CLOSE_THRESHOLD) {
      onClose();
    }
    setSwipeOffset(0);
  }, [isMobile, isSwiping, swipeOffset, onClose]);

  // 拖拽开始
  const handleDragStart = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      setIsDragging(true);
      dragStartX.current = e.clientX;
      dragStartWidth.current = panelWidth;
      document.body.style.userSelect = 'none';
      document.body.style.cursor = 'col-resize';
    },
    [panelWidth],
  );

  // WAI-ARIA window splitter：面板右停靠，左键加宽、右键收窄，Home/End 跳到边界
  const handleSeparatorKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      let target: number;
      switch (e.key) {
        case 'ArrowLeft':
          target = panelWidth + KEYBOARD_STEP;
          break;
        case 'ArrowRight':
          target = panelWidth - KEYBOARD_STEP;
          break;
        case 'Home':
          target = MIN_PANEL_WIDTH;
          break;
        case 'End':
          target = MAX_PANEL_WIDTH;
          break;
        default:
          return;
      }
      e.preventDefault();
      onSetPanelWidth(Math.min(MAX_PANEL_WIDTH, Math.max(MIN_PANEL_WIDTH, target)));
    },
    [panelWidth, onSetPanelWidth],
  );

  // 拖拽移动和结束
  useEffect(() => {
    if (!isDragging) {
      return;
    }

    const handleDragMove = (e: MouseEvent) => {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current);
      }
      rafRef.current = requestAnimationFrame(() => {
        const delta = dragStartX.current - e.clientX;
        const rawWidth = dragStartWidth.current + delta;
        const clampedWidth = Math.min(MAX_PANEL_WIDTH, Math.max(MIN_PANEL_WIDTH, rawWidth));
        onSetPanelWidth(clampedWidth);
      });
    };

    const handleDragEnd = () => {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
      setIsDragging(false);
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
    };

    document.addEventListener('mousemove', handleDragMove);
    document.addEventListener('mouseup', handleDragEnd);

    return () => {
      document.removeEventListener('mousemove', handleDragMove);
      document.removeEventListener('mouseup', handleDragEnd);
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current);
      }
    };
  }, [isDragging, onSetPanelWidth]);

  return {
    swipeOffset,
    isSwiping,
    handleTouchStart,
    handleTouchMove,
    handleTouchEnd,
    isDragging,
    separatorProps: {
      role: 'separator',
      tabIndex: 0,
      'aria-orientation': 'vertical',
      'aria-valuenow': panelWidth,
      'aria-valuemin': MIN_PANEL_WIDTH,
      'aria-valuemax': MAX_PANEL_WIDTH,
      onMouseDown: handleDragStart,
      onKeyDown: handleSeparatorKeyDown,
    },
  };
}
