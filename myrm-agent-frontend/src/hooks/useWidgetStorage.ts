/**
 * [INPUT]
 * - @/lib/api::apiRequest (POS: 统一 API 请求入口)
 *
 * [OUTPUT]
 * - useWidgetStorage: hook — Manages widget KV storage bridge lifecycle.
 *   Returns storageData for iframe hydration and a handleStorageMessage callback.
 *
 * [POS]
 * Bridges sandboxed iframe localStorage polyfill with server-side SQLite persistence.
 * Handles debounced batch writes, single-key deletes, and namespace-level clear.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { apiRequest, getApiUrl } from '@/lib/api';

interface StorageBatchEntry {
  key: string;
  value: string;
}

interface WidgetStorageOptions {
  namespace: string | undefined;
  chatId: string | undefined;
  enabled?: boolean;
}

interface WidgetStorageResult {
  storageData: Record<string, string> | undefined;
  handleStorageMessage: (data: Record<string, unknown>) => void;
}

const DEBOUNCE_MS = 300;

/**
 * Hook to manage widget KV storage bridge for sandboxed iframes.
 * Fetches initial data on mount and handles postMessage-based storage operations.
 */
export function useWidgetStorage({ namespace, chatId, enabled = true }: WidgetStorageOptions): WidgetStorageResult {
  const [storageData, setStorageData] = useState<Record<string, string> | undefined>(undefined);
  const pendingWritesRef = useRef<Map<string, string>>(new Map());
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const namespaceRef = useRef(namespace);
  const chatIdRef = useRef(chatId);

  namespaceRef.current = namespace;
  chatIdRef.current = chatId;

  useEffect(() => {
    if (!enabled || !namespace) {
      setStorageData(undefined);
      return;
    }

    let cancelled = false;

    async function load() {
      try {
        const resp = await apiRequest<{ data: Record<string, string> }>(`/widget-storage/${namespace}/all`);
        if (!cancelled) {
          setStorageData(resp.data ?? {});
        }
      } catch {
        if (!cancelled) setStorageData({});
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [enabled, namespace]);

  const flush = useCallback((keepalive = false) => {
    const ns = namespaceRef.current;
    const cId = chatIdRef.current;
    if (!ns || !cId) return;

    const entries: StorageBatchEntry[] = [];
    pendingWritesRef.current.forEach((value, key) => {
      entries.push({ key, value });
    });
    pendingWritesRef.current.clear();
    timerRef.current = null;

    if (!entries.length) return;

    if (keepalive) {
      fetch(getApiUrl(`/widget-storage/${ns}/batch`), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chat_id: cId, entries }),
        keepalive: true,
      }).catch(() => {});
    } else {
      apiRequest(`/widget-storage/${ns}/batch`, {
        method: 'PUT',
        body: JSON.stringify({ chat_id: cId, entries }),
      }).catch((err: unknown) => {
        console.warn('[WidgetStorage] batch write failed:', err);
      });
    }
  }, []);

  useEffect(() => {
    const handleBeforeUnload = () => {
      if (pendingWritesRef.current.size > 0) {
        flush(true);
      }
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        flush();
      }
    };
  }, [flush]);

  const handleStorageMessage = useCallback(
    (data: Record<string, unknown>) => {
      const ns = namespaceRef.current;
      if (!ns || !enabled) return;

      if (data.type === 'widget-storage-batch') {
        const entries = data.entries as StorageBatchEntry[] | undefined;
        if (!entries?.length) return;

        for (const { key, value } of entries) {
          pendingWritesRef.current.set(key, value);
        }

        if (timerRef.current) clearTimeout(timerRef.current);
        timerRef.current = setTimeout(flush, DEBOUNCE_MS);

        setStorageData((prev) => {
          const next = { ...prev };
          for (const { key, value } of entries) {
            next[key] = value;
          }
          return next;
        });
      }

      if (data.type === 'widget-storage-remove') {
        const key = data.key as string;
        if (!key) return;

        apiRequest(`/widget-storage/${ns}/${encodeURIComponent(key)}`, {
          method: 'DELETE',
        }).catch((err: unknown) => {
          console.warn('[WidgetStorage] delete failed:', err);
        });

        setStorageData((prev) => {
          if (!prev) return prev;
          const next = { ...prev };
          delete next[key];
          return next;
        });
      }

      if (data.type === 'widget-storage-clear') {
        apiRequest(`/widget-storage/${ns}/all`, {
          method: 'DELETE',
        }).catch((err: unknown) => {
          console.warn('[WidgetStorage] clear failed:', err);
        });

        setStorageData({});
      }
    },
    [enabled, flush],
  );

  return { storageData, handleStorageMessage };
}
