/**
 * [INPUT]
 * - columnRef: 消息列容器
 *
 * [OUTPUT]
 * - useMessageInputWidth: 把消息列宽度写入 `--message-input-width`，输入框据此与消息列同宽
 *
 * [POS]
 * Chat 的布局同步层。挂载时与窗口缩放停止 100ms 后各测一次，测不到宽度时回落到 740px。
 */

import { useEffect, useRef, type RefObject } from 'react';

export function useMessageInputWidth(columnRef: RefObject<HTMLElement | null>): void {
  const resizeTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => {
    // Every call restarts the 100ms wait, so a window drag is measured once, after it stops.
    const updateContainerWidth = () => {
      clearTimeout(resizeTimerRef.current);
      resizeTimerRef.current = setTimeout(() => {
        if (columnRef.current) {
          document.documentElement.style.setProperty(
            '--message-input-width',
            `${columnRef.current.scrollWidth || 740}px`,
          );
        }
      }, 100);
    };

    updateContainerWidth();
    window.addEventListener('resize', updateContainerWidth);
    return () => {
      clearTimeout(resizeTimerRef.current);
      window.removeEventListener('resize', updateContainerWidth);
    };
  }, [columnRef]);
}
