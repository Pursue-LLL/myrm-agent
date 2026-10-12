'use client';

import { useEffect } from 'react';

import { desktopBridge, installExternalLinkPolicy } from '@/lib/desktop-bridge';
import { isTauriEnvironment } from '@/lib/tauri';

/**
 * Inside the Tauri shell, routes window.open new-window requests for http(s) URLs to the system browser
 * (the shell drops them). Renders nothing; outside the shell it is a no-op so browsers keep their own
 * popup handling.
 */
export default function ExternalLinkInitializer() {
  useEffect(() => {
    if (!isTauriEnvironment()) {
      return undefined;
    }
    return installExternalLinkPolicy(window, (url) => desktopBridge.shell.openExternalUrl(url));
  }, []);

  return null;
}
