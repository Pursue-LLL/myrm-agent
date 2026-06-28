'use client';

/**
 * [POS] 版本变更感知 Hook
 *
 * 启动时对比 localStorage 中的上次已查看版本与当前运行版本，
 * 若版本变更则从 GitHub Release API 拉取对应版本的 Release Notes。
 *
 * 仅在 Tauri 运行时生效，非 Tauri 环境永远不展示。
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { isTauriRuntime } from '@/lib/deploy-mode';

const LAST_SEEN_VERSION_KEY = 'myrm-whats-new-last-seen-version';
const RELEASE_API_BASE = 'https://api.github.com/repos/Pursue-LLL/myrm-agent/releases/tags';

export interface ReleaseInfo {
  version: string;
  body: string;
  publishedAt: string;
  htmlUrl: string;
}

export interface UseWhatsNewResult {
  visible: boolean;
  release: ReleaseInfo | null;
  loading: boolean;
  dismiss: () => void;
}

async function getCurrentVersion(): Promise<string | null> {
  if (!isTauriRuntime()) return null;
  try {
    const { getVersion } = await import('@tauri-apps/api/app');
    return await getVersion();
  } catch {
    return null;
  }
}

async function fetchRelease(version: string): Promise<ReleaseInfo | null> {
  try {
    const res = await fetch(`${RELEASE_API_BASE}/v${version}`, {
      headers: { Accept: 'application/vnd.github+json' },
    });
    if (!res.ok) return null;
    const data = await res.json();
    return {
      version,
      body: typeof data.body === 'string' ? data.body : '',
      publishedAt: typeof data.published_at === 'string' ? data.published_at : '',
      htmlUrl: typeof data.html_url === 'string' ? data.html_url : '',
    };
  } catch {
    return null;
  }
}

export function useWhatsNew(): UseWhatsNewResult {
  const [visible, setVisible] = useState(false);
  const [release, setRelease] = useState<ReleaseInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const checkedRef = useRef(false);

  useEffect(() => {
    if (checkedRef.current || !isTauriRuntime()) return;
    checkedRef.current = true;

    void (async () => {
      const currentVersion = await getCurrentVersion();
      if (!currentVersion) return;

      try {
        const lastSeen = localStorage.getItem(LAST_SEEN_VERSION_KEY);
        if (lastSeen === currentVersion) return;
      } catch {
        return;
      }

      setLoading(true);
      const info = await fetchRelease(currentVersion);
      setLoading(false);

      if (info && info.body.trim()) {
        setRelease(info);
        setVisible(true);
      } else {
        try {
          localStorage.setItem(LAST_SEEN_VERSION_KEY, currentVersion);
        } catch { /* quota exceeded — graceful degrade */ }
      }
    })();
  }, []);

  const dismiss = useCallback(() => {
    setVisible(false);
    if (release) {
      try {
        localStorage.setItem(LAST_SEEN_VERSION_KEY, release.version);
      } catch { /* quota exceeded — graceful degrade */ }
    }
  }, [release]);

  return { visible, release, loading, dismiss };
}
