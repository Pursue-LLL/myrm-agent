'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import useThemePackagePendingStore from '@/store/useThemePackagePendingStore';

interface ThemePackageOpenPayload {
  filename: string;
  dataBase64: string;
}

function decodeThemePackageFile(payload: ThemePackageOpenPayload): File {
  const binary = atob(payload.dataBase64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return new File([bytes], payload.filename, { type: 'application/zip' });
}

export function useThemePackageOpenListener(): void {
  const router = useRouter();
  const setPendingFile = useThemePackagePendingStore((state) => state.setPendingFile);

  useEffect(() => {
    const isTauri = typeof window !== 'undefined' && window.__TAURI_INTERNALS__ !== undefined;
    if (!isTauri) {
      return;
    }

    let unlisten: (() => void) | undefined;

    const setup = async () => {
      try {
        const { listen } = await import('@tauri-apps/api/event');
        unlisten = await listen<ThemePackageOpenPayload>('theme-package-open', async (event) => {
          const payload = event.payload;
          if (!payload?.dataBase64 || !payload.filename) {
            return;
          }
          try {
            const { getCurrentWindow } = await import('@tauri-apps/api/window');
            const appWindow = getCurrentWindow();
            await appWindow.show();
            await appWindow.unminimize();
            await appWindow.setFocus();
          } catch (error) {
            console.error('[ThemePackageOpenListener] Failed to focus window:', error);
          }
          setPendingFile(decodeThemePackageFile(payload));
          router.push('/settings/preferences');
        });
      } catch (error) {
        console.error('[ThemePackageOpenListener] Failed to register handler:', error);
      }
    };

    void setup();

    return () => {
      if (unlisten) {
        unlisten();
      }
    };
  }, [router, setPendingFile]);
}
