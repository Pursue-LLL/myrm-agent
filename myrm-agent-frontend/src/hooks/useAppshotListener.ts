'use client';

/**
 * [INPUT]
 * - Tauri event "appshot-captured" from global shortcut handler
 * - useFlowPadStore (POS: FlowPad modal state)
 *
 * [OUTPUT]
 * - Listens for Appshot events and opens FlowPad modal for user confirmation
 *
 * [POS]
 * Connects Tauri-side Appshot captures to FlowPad modal. Each capture
 * immediately opens/appends to the FlowPad, giving users the choice of
 * which Agent to route to and what instruction to attach.
 */

import { useEffect, useRef, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { isTauriRuntime } from '@/lib/deploy-mode';
import { toast } from '@/lib/utils/toast';
import { useFlowPadStore } from '@/store/useFlowPadStore';

interface AppshotPayload {
  screenshot: string;
  windowTitle: string;
  extractedText: string;
  needsPermission: boolean;
  timestamp: number;
}

export function useAppshotListener() {
  const t = useTranslations('appshot');
  const needsPermissionRef = useRef(false);
  const addCapture = useFlowPadStore((s) => s.addCapture);

  const handleCapture = useCallback(
    (payload: AppshotPayload) => {
      if (!payload.screenshot && !payload.extractedText?.trim()) {
        toast.error(t('captureFailed'), { duration: 3000 });
        return;
      }

      const prevCount = useFlowPadStore.getState().captures.length;

      if (payload.needsPermission && !needsPermissionRef.current) {
        needsPermissionRef.current = true;
        toast.warning(t('permissionRequired'), {
          description: t('permissionDescription'),
          duration: 15_000,
          dismissible: true,
          action: {
            label: t('openSettings'),
            onClick: () => {
              import('@tauri-apps/plugin-shell')
                .then((mod) =>
                  mod.open('x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility'),
                )
                .catch(() => {
                  window.open(
                    'https://support.apple.com/guide/mac-help/allow-accessibility-apps-to-access-your-mac-mh43185/mac',
                    '_blank',
                  );
                });
            },
          },
        });
      }

      addCapture({
        screenshot: payload.screenshot,
        windowTitle: payload.windowTitle,
        extractedText: payload.extractedText,
        timestamp: payload.timestamp,
      });

      const newCount = useFlowPadStore.getState().captures.length;
      if (newCount === prevCount) {
        toast.warning(t('maxCapturesReached'), { duration: 3000 });
      } else {
        toast.success(t('captured', { count: 1 }), { duration: 2000 });
      }
    },
    [addCapture, t],
  );

  useEffect(() => {
    if (!isTauriRuntime()) return;

    let unlisten: (() => void) | undefined;

    const setup = async () => {
      try {
        const { listen } = await import('@tauri-apps/api/event');
        const unlistenFn = await listen<AppshotPayload>('appshot-captured', (event) => {
          handleCapture(event.payload);
        });
        unlisten = unlistenFn;
      } catch (err) {
        console.error('Failed to setup appshot listener:', err);
      }
    };

    setup();

    return () => {
      unlisten?.();
    };
  }, [handleCapture]);

  return { needsPermission: needsPermissionRef.current };
}
