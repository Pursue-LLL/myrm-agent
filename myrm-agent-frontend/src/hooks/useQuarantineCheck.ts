import { useState, useEffect } from 'react';
import { isTauriEnvironment, listenTauriEvent } from '@/lib/tauri';

export function useQuarantineCheck() {
  const [isQuarantined, setIsQuarantined] = useState(false);

  useEffect(() => {
    // 仅在 Tauri 环境中监听隔离检测事件
    if (!isTauriEnvironment()) {
      return;
    }

    let unlisten: (() => void) | null = null;

    listenTauriEvent('quarantine-detected', () => {
      console.warn('macOS Quarantine detected and silent heal failed.');
      setIsQuarantined(true);
    }).then((fn) => {
      unlisten = fn;
    });

    return () => {
      unlisten?.();
    };
  }, []);

  return {
    isQuarantined,
    setIsQuarantined,
  };
}
