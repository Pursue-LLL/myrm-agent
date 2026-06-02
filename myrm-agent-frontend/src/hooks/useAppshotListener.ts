'use client';

/**
 * [INPUT]
 * - Tauri event "appshot-captured" from global shortcut handler
 * - useChatStore (POS: chat state & sendMessage)
 *
 * [OUTPUT]
 * - Listens for Appshot events and sends grouped screenshots as user messages
 *
 * [POS]
 * Connects Tauri-side Appshot captures to frontend chat. Groups captures
 * within BATCH_WINDOW_MS into a single message to avoid flooding.
 */

import { useEffect, useRef, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { isTauriRuntime } from '@/lib/deploy-mode';
import { toast } from '@/lib/utils/toast';

interface AppshotPayload {
  screenshot: string;
  windowTitle: string;
  extractedText: string;
  needsPermission: boolean;
  timestamp: number;
}

interface AppshotCapture {
  screenshot: string;
  windowTitle: string;
  extractedText: string;
  timestamp: number;
}

const BATCH_WINDOW_MS = 60_000;
const MAX_BATCH_SIZE = 5;
const MAX_TEXT_PER_CAPTURE = 4000;

function formatAppshotMessage(captures: AppshotCapture[]): string {
  if (captures.length === 0) return '';

  const parts: string[] = ['[Appshot Context]'];

  for (const cap of captures) {
    const header = cap.windowTitle ? `**${cap.windowTitle}**` : 'Screen Capture';
    parts.push(`\n---\n${header}`);
    if (cap.extractedText.trim()) {
      const truncated =
        cap.extractedText.length > MAX_TEXT_PER_CAPTURE
          ? cap.extractedText.slice(0, MAX_TEXT_PER_CAPTURE) + '\n...(truncated)'
          : cap.extractedText;
      parts.push(`\`\`\`\n${truncated}\n\`\`\``);
    }
  }

  return parts.join('\n');
}

export function useAppshotListener() {
  const t = useTranslations('appshot');
  const batchRef = useRef<AppshotCapture[]>([]);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const needsPermissionRef = useRef(false);

  const flushBatch = useCallback(async () => {
    const captures = batchRef.current.slice();
    batchRef.current = [];
    timerRef.current = null;

    if (captures.length === 0) return;

    try {
      const useChatStore = (await import('@/store/useChatStore')).default;
      const store = useChatStore.getState();

      const screenshotFiles = captures
        .filter((c) => c.screenshot)
        .map((c, idx) => ({
          fileName: `appshot_${idx + 1}.jpg`,
          fileExtension: 'jpg',
          fileUrl: `data:image/jpeg;base64,${c.screenshot}`,
          fileType: 'uploaded' as const,
        }));

      if (screenshotFiles.length > 0) {
        store.setFiles([...store.files, ...screenshotFiles]);
      }

      const text = formatAppshotMessage(captures);
      if (text) {
        await store.sendMessage(text);
      }
    } catch (err) {
      console.error('Failed to process appshot batch:', err);
    }
  }, []);

  const handleCapture = useCallback(
    (payload: AppshotPayload) => {
      if (!payload.screenshot && !payload.extractedText?.trim()) {
        toast.error(t('captureFailed'), { duration: 3000 });
        return;
      }

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

      batchRef.current.push({
        screenshot: payload.screenshot,
        windowTitle: payload.windowTitle,
        extractedText: payload.extractedText,
        timestamp: payload.timestamp,
      });

      const count = batchRef.current.length;
      toast.success(t('captured', { count }), { duration: 2000 });

      if (batchRef.current.length >= MAX_BATCH_SIZE) {
        if (timerRef.current) {
          clearTimeout(timerRef.current);
          timerRef.current = null;
        }
        flushBatch();
        return;
      }

      if (!timerRef.current) {
        timerRef.current = setTimeout(flushBatch, BATCH_WINDOW_MS);
      }
    },
    [flushBatch, t],
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
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
    };
  }, [handleCapture]);

  return { needsPermission: needsPermissionRef.current };
}
