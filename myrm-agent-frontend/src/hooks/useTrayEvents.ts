import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { isTauriRuntime } from '@/lib/deploy-mode';

const TRAY_ROUTES: Record<string, string> = {
  'tray:new_chat': '/',
  'tray:settings': '/settings',
  'tray:workspace': '/workspace',
};

export function useTrayEvents() {
  const router = useRouter();

  useEffect(() => {
    if (!isTauriRuntime()) return;

    const unlisteners: (() => void)[] = [];

    const setup = async () => {
      try {
        const { listen } = await import('@tauri-apps/api/event');
        for (const [event, route] of Object.entries(TRAY_ROUTES)) {
          const unlisten = await listen(event, () => router.push(route));
          unlisteners.push(unlisten);
        }
      } catch (error) {
        console.error('Failed to setup tray event listeners:', error);
      }
    };

    setup();

    return () => {
      for (const unlisten of unlisteners) {
        unlisten();
      }
    };
  }, [router]);
}
