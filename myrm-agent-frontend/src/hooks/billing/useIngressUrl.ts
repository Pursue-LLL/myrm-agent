'use client';

import { useState, useEffect } from 'react';

import { systemService } from '@/services/system';
import useConfigStore from '@/store/useConfigStore';

function buildWebhookUrl(ingressBase: string, fallbackPath: string): string {
  const base = ingressBase.trim().replace(/\/$/, '');
  if (!base) {
    return (typeof window !== 'undefined' ? window.location.origin : '') + fallbackPath;
  }
  return base + fallbackPath;
}

export function useIngressUrl(fallbackPath = '') {
  const publicIngressBaseUrl = useConfigStore((s) => s.publicIngressBaseUrl);
  const [url, setUrl] = useState<string>('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function fetchUrl() {
      setLoading(true);
      try {
        const ingressUrl = await systemService.getIngressUrl();
        if (!cancelled) {
          setUrl(buildWebhookUrl(ingressUrl, fallbackPath));
        }
      } catch {
        if (!cancelled) {
          setUrl(buildWebhookUrl(publicIngressBaseUrl || '', fallbackPath));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void fetchUrl();
    return () => {
      cancelled = true;
    };
  }, [fallbackPath, publicIngressBaseUrl]);

  return { url, loading };
}
