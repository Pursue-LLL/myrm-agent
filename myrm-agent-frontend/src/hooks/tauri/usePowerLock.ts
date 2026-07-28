/**
 * [INPUT]
 * @/store/useChatStore::useChatStore (POS: Chat conversation state store)
 * @/lib/deploy-mode::isTauriRuntime (POS: Deployment mode detector)
 *
 * [OUTPUT]
 * usePowerLock: Prevents system sleep during agent task execution on desktop.
 *
 * [POS]
 * Desktop power management hook. Acquires a system power lock when agent
 * tasks are running and releases it when idle. Only active in Tauri runtime.
 */
import { useEffect } from 'react';
import { isTauriRuntime } from '@/lib/deploy-mode';
import useChatStore from '@/store/useChatStore';

export function usePowerLock() {
  const isGenerating = useChatStore((state) => state.loading);

  useEffect(() => {
    if (!isTauriRuntime()) return;

    const managePowerLock = async () => {
      try {
        const { invoke } = await import('@tauri-apps/api/core');
        if (isGenerating) {
          await invoke('power_lock_acquire', { reason: 'Agent task in progress' });
        } else {
          await invoke('power_lock_release');
        }
      } catch {
        // Non-critical: silently ignore if power management unavailable
      }
    };

    managePowerLock();
  }, [isGenerating]);
}
