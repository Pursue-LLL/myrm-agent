'use client';

/**
 * [POS] Tauri 桌面端自动更新 Hook
 *
 * 封装 @tauri-apps/plugin-updater 官方 JS API，提供完整的更新状态机：
 * idle → checking → available → downloading → ready → installing → restarting → up_to_date | error
 *
 * 仅在 Tauri 运行时生效，非 Tauri 环境静默返回 idle。
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { isTauriRuntime } from '@/lib/deploy-mode';

export type AppUpdatePhase =
  | 'idle'
  | 'checking'
  | 'available'
  | 'downloading'
  | 'ready'
  | 'installing'
  | 'restarting'
  | 'up_to_date'
  | 'error';

export interface AppUpdateInfo {
  currentVersion: string;
  version: string;
  body: string;
}

export interface UseAppUpdateOptions {
  autoCheck?: boolean;
  initialCheckDelayMs?: number;
  recheckIntervalMs?: number;
  autoDownload?: boolean;
}

export interface UseAppUpdateResult {
  phase: AppUpdatePhase;
  info: AppUpdateInfo | null;
  bytesDownloaded: number;
  totalBytes: number | null;
  error: string | null;
  check: () => Promise<void>;
  install: () => Promise<void>;
  reset: () => void;
}

const DEFAULT_INITIAL_DELAY_MS = 5_000;
const DEFAULT_RECHECK_INTERVAL_MS = 15 * 60 * 1000;
const AUTO_DOWNLOAD_GRACE_MS = 1_000;

type UpdaterModule = typeof import('@tauri-apps/plugin-updater');
type TauriInvoke = typeof import('@tauri-apps/api/core').invoke;

let updaterModule: UpdaterModule | null = null;
let tauriInvoke: TauriInvoke | null = null;

async function getUpdaterModule(): Promise<UpdaterModule | null> {
  if (updaterModule) return updaterModule;
  if (!isTauriRuntime()) return null;
  try {
    updaterModule = await import('@tauri-apps/plugin-updater');
    return updaterModule;
  } catch {
    return null;
  }
}

async function getTauriInvoke(): Promise<TauriInvoke | null> {
  if (tauriInvoke) return tauriInvoke;
  if (!isTauriRuntime()) return null;
  try {
    const coreModule = await import('@tauri-apps/api/core');
    tauriInvoke = coreModule.invoke;
    return tauriInvoke;
  } catch {
    return null;
  }
}

export function useAppUpdate(options: UseAppUpdateOptions = {}): UseAppUpdateResult {
  const {
    autoCheck = true,
    initialCheckDelayMs = DEFAULT_INITIAL_DELAY_MS,
    recheckIntervalMs = DEFAULT_RECHECK_INTERVAL_MS,
    autoDownload = true,
  } = options;

  const [phase, setPhase] = useState<AppUpdatePhase>('idle');
  const [info, setInfo] = useState<AppUpdateInfo | null>(null);
  const [bytesDownloaded, setBytesDownloaded] = useState(0);
  const [totalBytes, setTotalBytes] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const mountedRef = useRef(true);
  const phaseRef = useRef(phase);
  phaseRef.current = phase;
  const downloadInFlightRef = useRef(false);
  // Holds the pending Update object between check and install
  const pendingUpdateRef = useRef<Awaited<ReturnType<UpdaterModule['check']>> | null>(null);

  const check = useCallback(async () => {
    if (!isTauriRuntime()) return;
    const busy =
      phaseRef.current === 'downloading' || phaseRef.current === 'ready' || phaseRef.current === 'installing';
    if (busy) return;

    setPhase('checking');
    setError(null);

    try {
      const mod = await getUpdaterModule();
      if (!mod || !mountedRef.current) return;

      const update = await mod.check();
      if (!mountedRef.current) return;

      if (update) {
        pendingUpdateRef.current = update;
        setInfo({
          currentVersion: update.currentVersion,
          version: update.version,
          body: update.body ?? '',
        });
        setPhase('available');
        console.debug(`[app-update] update available: ${update.currentVersion} → ${update.version}`);
      } else {
        setPhase('up_to_date');
        console.debug('[app-update] already up to date');
      }
    } catch (err) {
      if (!mountedRef.current) return;
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      setPhase('error');
      console.warn('[app-update] check failed:', msg);
    }
  }, []);

  const doDownload = useCallback(async () => {
    const update = pendingUpdateRef.current;
    if (!update || downloadInFlightRef.current) return;

    downloadInFlightRef.current = true;
    setBytesDownloaded(0);
    setTotalBytes(null);
    setPhase('downloading');
    setError(null);

    try {
      await update.download((event) => {
        if (!mountedRef.current) return;
        if (event.event === 'Started') {
          setTotalBytes(event.data.contentLength ?? null);
        } else if (event.event === 'Progress') {
          setBytesDownloaded((prev) => prev + event.data.chunkLength);
        }
      });

      if (!mountedRef.current) return;
      setPhase('ready');
      console.debug('[app-update] download complete, ready to install');
    } catch (err) {
      if (!mountedRef.current) return;
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      setPhase('error');
      console.warn('[app-update] download failed:', msg);
    } finally {
      downloadInFlightRef.current = false;
    }
  }, []);

  const install = useCallback(async () => {
    const update = pendingUpdateRef.current;
    if (!update) return;

    setPhase('installing');
    setError(null);
    console.debug('[app-update] installing update…');

    try {
      await update.install();
      if (!mountedRef.current) return;
      setPhase('restarting');

      const invoke = await getTauriInvoke();
      if (invoke) {
        console.debug('[app-update] relaunching app…');
        await invoke('restart_app');
      }
    } catch (err) {
      if (!mountedRef.current) return;
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      setPhase('error');
      console.warn('[app-update] install failed:', msg);
    }
  }, []);

  const reset = useCallback(() => {
    setError(null);
    setBytesDownloaded(0);
    setTotalBytes(null);
    const resettable =
      phaseRef.current === 'error' || phaseRef.current === 'up_to_date' || phaseRef.current === 'available';
    if (resettable) {
      setPhase('idle');
    }
  }, []);

  // Auto-check cadence
  useEffect(() => {
    if (!autoCheck || !isTauriRuntime()) return;

    const initialTimer = setTimeout(
      () => {
        void check();
      },
      Math.max(0, initialCheckDelayMs),
    );

    let recheckTimer: ReturnType<typeof setInterval> | undefined;
    if (recheckIntervalMs > 0) {
      recheckTimer = setInterval(() => {
        void check();
      }, recheckIntervalMs);
    }

    return () => {
      clearTimeout(initialTimer);
      if (recheckTimer) clearInterval(recheckTimer);
    };
  }, [autoCheck, initialCheckDelayMs, recheckIntervalMs, check]);

  // Auto-download when available
  useEffect(() => {
    if (!autoDownload || !isTauriRuntime()) return;
    if (phase !== 'available') return;
    if (downloadInFlightRef.current) return;

    const timer = setTimeout(() => {
      void doDownload();
    }, AUTO_DOWNLOAD_GRACE_MS);
    return () => clearTimeout(timer);
  }, [autoDownload, phase, doDownload]);

  // Cleanup
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  return { phase, info, bytesDownloaded, totalBytes, error, check, install, reset };
}
