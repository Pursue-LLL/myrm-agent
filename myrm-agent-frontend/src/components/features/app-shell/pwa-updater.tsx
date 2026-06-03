'use client';

import { useEffect } from 'react';
import { toast } from 'sonner';
import { useTranslations } from 'next-intl';

/**
 * [POS] PWA Version Updater Component
 * Listens for Service Worker updates. If a new version is downloaded and waiting,
 * it prompts the user to refresh the page to apply the update, preventing cache deadlocks.
 */
export function PWAUpdater() {
  const t = useTranslations('appUpdate');

  useEffect(() => {
    if (typeof window === 'undefined' || !('serviceWorker' in navigator)) {
      return;
    }

    if (window.__TAURI_INTERNALS__) {
      return;
    }

    let refreshing = false;

    navigator.serviceWorker.addEventListener('controllerchange', () => {
      if (!refreshing) {
        refreshing = true;
        window.location.reload();
      }
    });

    navigator.serviceWorker
      .register('/sw.js')
      .then((registration) => {
        console.log('[PWA] ServiceWorker registration successful with scope: ', registration.scope);

        if (registration.waiting) {
          showUpdateToast(registration.waiting);
        }

        registration.addEventListener('updatefound', () => {
          const newWorker = registration.installing;
          if (newWorker) {
            newWorker.addEventListener('statechange', () => {
              if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                showUpdateToast(newWorker);
              }
            });
          }
        });
      })
      .catch((err) => {
        console.log('[PWA] ServiceWorker registration failed: ', err);
      });

    function showUpdateToast(worker: ServiceWorker) {
      toast(t('pwaNewVersion'), {
        description: t('pwaDescription'),
        duration: Number.POSITIVE_INFINITY,
        action: {
          label: t('pwaRefresh'),
          onClick: () => {
            worker.postMessage({ type: 'SKIP_WAITING' });
          },
        },
      });
    }
  }, [t]);

  return null;
}
