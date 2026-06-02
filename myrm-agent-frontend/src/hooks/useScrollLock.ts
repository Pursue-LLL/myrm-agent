import { useEffect, useRef } from 'react';

/**
 * useScrollLock - Prevent scroll penetration when modal/portal is open
 * 防止弹窗打开时的滚动穿透
 *
 * @param isLocked - Whether to lock the scroll / 是否锁定滚动
 *
 * Features / 特性:
 * - Locks body scroll when modal is open / 弹窗打开时锁定 body 滚动
 * - Preserves scroll position / 保持滚动位置
 * - Supports multiple modals / 支持多个弹窗同时存在
 * - Prevents layout shift / 防止布局抖动
 */
export function useScrollLock(isLocked: boolean): void {
  const scrollPositionRef = useRef<number>(0);

  useEffect(() => {
    // Only run on client side / 仅在客户端运行
    if (typeof window === 'undefined') return;

    const body = document.body;
    const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth;

    if (isLocked) {
      // Save current scroll position / 保存当前滚动位置
      scrollPositionRef.current = window.scrollY;

      // Apply scroll lock styles / 应用滚动锁定样式
      const originalStyles = {
        overflow: body.style.overflow,
        position: body.style.position,
        top: body.style.top,
        width: body.style.width,
        paddingRight: body.style.paddingRight,
      };

      // Lock body scroll / 锁定 body 滚动
      body.style.overflow = 'hidden';
      body.style.position = 'fixed';
      body.style.top = `-${scrollPositionRef.current}px`;
      body.style.width = '100%';

      // Compensate for scrollbar width to prevent layout shift
      // 补偿滚动条宽度以防止布局抖动
      if (scrollbarWidth > 0) {
        body.style.paddingRight = `${scrollbarWidth}px`;
      }

      // Cleanup function / 清理函数
      return () => {
        // Restore original styles / 恢复原始样式
        body.style.overflow = originalStyles.overflow;
        body.style.position = originalStyles.position;
        body.style.top = originalStyles.top;
        body.style.width = originalStyles.width;
        body.style.paddingRight = originalStyles.paddingRight;

        // Restore scroll position / 恢复滚动位置
        window.scrollTo(0, scrollPositionRef.current);
      };
    }
  }, [isLocked]);
}
