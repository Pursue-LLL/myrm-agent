/**
 * [INPUT]
 * @/store/useChatStore::useChatStore (POS: Chat conversation state store)
 * @/lib/deploy-mode::isTauriRuntime (POS: Deployment mode detector)
 *
 * [OUTPUT]
 * useTrayStatus: Synchronizes Tauri tray tooltip, taskbar progress bar,
 * and completion bounce notification with chat streaming activity.
 *
 * [POS]
 * Desktop tray bridge hook. It mirrors chat generation state to the system
 * tray, taskbar progress bar (macOS Dock / Windows taskbar), and fires a
 * user-attention bounce when a task finishes while the window is not focused.
 * Remains inert in non-Tauri environments.
 */
import { useEffect, useRef } from 'react';
import { isTauriRuntime } from '@/lib/deploy-mode';
import useChatStore from '@/store/useChatStore';

export function useTrayStatus() {
  const isGenerating = useChatStore((state) => state.loading);
  const prevGenerating = useRef(false);

  useEffect(() => {
    if (!isTauriRuntime()) return;

    const sync = async () => {
      try {
        const [{ invoke }, { getCurrentWindow, ProgressBarStatus }] = await Promise.all([
          import('@tauri-apps/api/core'),
          import('@tauri-apps/api/window'),
        ]);

        const status = isGenerating ? 'busy' : 'idle';
        await invoke('set_tray_status', { status });

        const win = getCurrentWindow();

        if (isGenerating) {
          await win.setProgressBar({ status: ProgressBarStatus.Indeterminate });
        } else {
          await win.setProgressBar({ status: ProgressBarStatus.None });

          if (prevGenerating.current && document.visibilityState === 'hidden') {
            await win.requestUserAttention(2); // Informational
          }
        }
      } catch {
        // Tauri API unavailable or permission denied — silently ignore
      }

      prevGenerating.current = isGenerating;
    };

    sync();
  }, [isGenerating]);
}
