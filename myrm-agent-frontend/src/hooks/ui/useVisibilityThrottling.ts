import { useEffect } from 'react';
import { isTauriRuntime } from '@/lib/deploy-mode';

/**
 * 前端可见性节流 Hook
 *
 * 当应用窗口被隐藏到托盘或最小化时，暂停不必要的轮询和动画。
 * 依赖于浏览器的 Page Visibility API。在 Tauri 中，window.hide() 会触发 visibilitychange。
 */
export function useVisibilityThrottling() {
  useEffect(() => {
    // 即使在 Web 模式下，Page Visibility API 也是有用的
    const handleVisibilityChange = () => {
      const isVisible = document.visibilityState === 'visible';

      if (!isVisible) {
        console.log('App hidden: Throttling background tasks...');
        // 这里可以触发全局事件或直接调用其他 store 暂停轮询
        // 例如：设置一个全局 CSS 变量来暂停所有 CSS 动画
        document.documentElement.style.setProperty('--app-visible', '0');
      } else {
        console.log('App visible: Resuming tasks...');
        document.documentElement.style.setProperty('--app-visible', '1');
      }
    };

    // 初始化设置
    handleVisibilityChange();

    document.addEventListener('visibilitychange', handleVisibilityChange);

    // Tauri 特定事件监听 (作为补充)
    let unlisten: (() => void) | undefined;
    if (isTauriRuntime()) {
      import('@tauri-apps/api/window')
        .then(({ getCurrentWindow }) => {
          const appWindow = getCurrentWindow();
          appWindow
            .onFocusChanged(({ payload: focused }) => {
              if (!focused && document.visibilityState !== 'visible') {
                document.documentElement.style.setProperty('--app-visible', '0');
              } else if (focused) {
                document.documentElement.style.setProperty('--app-visible', '1');
              }
            })
            .then((u) => (unlisten = u));
        })
        .catch(console.error);
    }

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      if (unlisten) unlisten();
    };
  }, []);
}
