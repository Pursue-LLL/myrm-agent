/**
 * [INPUT]
 * @/store/useChatStore::useChatStore (POS: Chat conversation state store)
 * @/lib/desktop-bridge::desktopBridge (POS: 统一桌面桥接门面)
 *
 * [OUTPUT]
 * usePowerLock: Prevents system sleep during agent task execution on desktop.
 *
 * [POS]
 * Desktop power management hook. Acquires a system power lock when agent
 * tasks are running and releases it when idle. Driven through IDesktopBridge.power.
 */
import { useEffect, useRef } from 'react';
import { desktopBridge } from '@/lib/desktop-bridge';
import useChatStore from '@/store/useChatStore';

export function usePowerLock() {
  const isGenerating = useChatStore((state) => state.loading);
  const lockIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (!desktopBridge.isDesktop || !desktopBridge.capabilities.hasNativePowerLock) {
      return;
    }

    const managePowerLock = async () => {
      try {
        if (isGenerating) {
          if (!lockIdRef.current) {
            const id = await desktopBridge.power.acquireLock('Agent task in progress');
            lockIdRef.current = id;
          }
        } else {
          if (lockIdRef.current) {
            await desktopBridge.power.releaseLock(lockIdRef.current);
            lockIdRef.current = null;
          }
        }
      } catch {
        // Non-critical: silently ignore if power management unavailable
      }
    };

    void managePowerLock();
  }, [isGenerating]);
}
