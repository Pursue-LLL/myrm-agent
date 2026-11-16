'use client';

import { useEffect } from 'react';

export async function unregisterServiceWorkers(container: ServiceWorkerContainer): Promise<void> {
  const registrations = await container.getRegistrations();
  await Promise.all(registrations.map((registration) => registration.unregister()));
}

/**
 * [INPUT]
 * - navigator.serviceWorker (register / getRegistrations)
 * - window.__TAURI_INTERNALS__ (marker of the desktop shell)
 *
 * [OUTPUT]
 * - ServiceWorkerRegistrar: registers the Web Push worker in production web builds
 * - unregisterServiceWorkers: drops every registration (development)
 *
 * [POS]
 * Service Worker registrar, mounted once by deferred-app-initializers. Registers `/sw.js` with the default
 * scope in production web builds, unregisters existing workers in development, and does nothing inside the
 * Tauri shell. Push subscriptions hang on this registration, so URL and scope stay fixed.
 */
export function ServiceWorkerRegistrar() {
  useEffect(() => {
    if (typeof window === 'undefined' || !('serviceWorker' in navigator)) {
      return;
    }

    if (window.__TAURI_INTERNALS__) {
      return;
    }

    if (process.env.NODE_ENV === 'development') {
      void unregisterServiceWorkers(navigator.serviceWorker).catch((error: unknown) => {
        console.warn('[PWA] Failed to unregister development ServiceWorker:', error);
      });
      return;
    }

    navigator.serviceWorker.register('/sw.js').catch((error: unknown) => {
      console.warn('[PWA] ServiceWorker registration failed:', error);
    });
  }, []);

  return null;
}
