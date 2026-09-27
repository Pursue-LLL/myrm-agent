'use client';

/**
 * [INPUT]
 * @/hooks/tauri/useAppUpdate::useAppUpdate (POS: Tauri OTA updater hook)
 * @/lib/update-prefs (POS: LocalStorage update preferences and quiet hours)
 * @/lib/deploy-mode::isTauriRuntime (POS: Deployment mode detection)
 *
 * [OUTPUT]
 * StackUpdatePanel: Renders the full-stack update status across Tauri, WebUI, and Cloud.
 *
 * [POS]
 * Central update status surface within Settings/About. Presents grouped changelogs,
 * version comparison, git behind status, and update preferences.
 */

import { memo, useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconCheck, IconShield } from '@/components/features/icons/PremiumIcons';
import { isTauriRuntime } from '@/lib/deploy-mode';
import { useAppUpdate } from '@/hooks/tauri/useAppUpdate';
import {
  getAutoBackup, getDeferredVersion, getQuietHours, isDeferred, isQuietNow,
  setAutoBackup, setDeferredVersion, setQuietHours,
  type QuietHours,
} from '@/lib/update-prefs';

interface SnapshotItem {
  snapshot_id: string;
  label: string;
  size_bytes: number;
  created_at: string;
  from_version?: string | null;
  to_version?: string | null;
}
import { cn } from '@/lib/utils/classnameUtils';

interface ChangelogGroups {
  fixed: string[];
  other: string[];
  grouped: boolean;
  is_security?: boolean;
}

interface UpdateStatusPayload {
  server_version?: string;
  harness_version?: string;
  latest?: { version?: string; published_at?: string; url?: string } | null;
  fetch_error?: string | null;
  stale?: boolean | null;
  changelog?: ChangelogGroups;
  git?: { behind_count?: number; log?: string[] } | null;
  prebuilt?: { synced_count?: number | null } | null;
  cloud?: { state?: string } | null;
}

const QUIET_OFF = 'off';

function parseHour(value: string): number | null {
  const hour = Number.parseInt(value, 10);
  return Number.isInteger(hour) && hour >= 0 && hour <= 23 ? hour : null;
}

export default function StackUpdatePanel() {
  const t = useTranslations('settings.system.stackUpdate');
  const [status, setStatus] = useState<UpdateStatusPayload | null>(null);
  const [statusError, setStatusError] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [deferredVersion, setDeferredVersionState] = useState<string | null>(null);
  const [quiet, setQuiet] = useState<QuietHours | null>(null);
  const [quietStart, setQuietStart] = useState<string>(QUIET_OFF);
  const [quietEnd, setQuietEnd] = useState<string>(QUIET_OFF);
  const [doctorResult, setDoctorResult] = useState<'pass' | 'fail' | null>(null);
  const [autoBackupEnabled, setAutoBackupState] = useState(true);
  const [snapshots, setSnapshots] = useState<SnapshotItem[]>([]);
  const [backupBusy, setBackupBusy] = useState(false);
  const [backupError, setBackupError] = useState(false);
  const [restoredId, setRestoredId] = useState<string | null>(null);
  const [isDoctoring, setIsDoctoring] = useState(false);

  const quietRef = useRef({ start: QUIET_OFF, end: QUIET_OFF });
  quietRef.current = { start: quietStart, end: quietEnd };

  const {
    phase: desktopPhase,
    info: desktopInfo,
    bytesDownloaded,
    totalBytes,
    error: desktopError,
    check: desktopCheck,
    install: desktopInstall,
  } = useAppUpdate({ autoCheck: false, autoDownload: false });

  const refreshStatus = useCallback(async () => {
    try {
      const response = await fetch('/api/v1/health/update-status');
      if (!response.ok) {
        setStatusError(true);
        return;
      }
      const payload = (await response.json()) as UpdateStatusPayload;
      setStatus(payload);
      setStatusError(false);
    } catch {
      setStatusError(true);
    }
  }, []);

  const refreshSnapshots = useCallback(async () => {
    try {
      const response = await fetch('/api/v1/system/storage/snapshots');
      if (!response.ok) {
        return;
      }
      const payload = (await response.json()) as { snapshots?: SnapshotItem[] };
      if (Array.isArray(payload.snapshots)) {
        setSnapshots(payload.snapshots);
      }
    } catch {
      // Snapshot list is best effort; the update panel works without it.
    }
  }, []);

  const snapshotBeforeInstall = useCallback(async (fromVersion: string, toVersion: string) => {
    if (!getAutoBackup()) {
      return;
    }
    try {
      await fetch('/api/v1/system/storage/snapshots/pre-update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ from_version: fromVersion, to_version: toVersion }),
      });
    } catch {
      // A failed pre-update snapshot must never block the update itself.
    }
  }, []);

  useEffect(() => {
    setDeferredVersionState(getDeferredVersion());
    setAutoBackupState(getAutoBackup());
    const initialQuiet = getQuietHours();
    setQuiet(initialQuiet);
    if (initialQuiet) {
      const s = String(initialQuiet.startHour);
      const e = String(initialQuiet.endHour);
      setQuietStart(s);
      setQuietEnd(e);
      quietRef.current = { start: s, end: e };
    }
    void refreshStatus();
    void refreshSnapshots();
  }, [refreshStatus, refreshSnapshots]);

  const latestVersion = status?.latest?.version ?? null;
  const isSecurity = status?.changelog?.is_security === true;
  const deferred = isDeferred(latestVersion);
  const quietNow = isQuietNow(quiet);
  const fixed = status?.changelog?.fixed ?? [];
  const other = status?.changelog?.other ?? [];
  const visibleFixed = expanded ? fixed : fixed.slice(0, 5);
  const visibleOther = expanded ? other : other.slice(0, 5);
  const downloadProgress =
    totalBytes && totalBytes > 0 ? Math.min(100, Math.round((bytesDownloaded / totalBytes) * 100)) : null;

  const handleDesktopInstall = useCallback(() => {
    // Post-restart success/failure feedback is owned by UpdateHandoffNotifier
    // (verified handoff); the hook records the handoff on install.
    if (desktopInfo) {
      void snapshotBeforeInstall(desktopInfo.currentVersion, desktopInfo.version).then(() => {
        void refreshSnapshots();
      });
    }
    void desktopInstall();
  }, [desktopInfo, desktopInstall, refreshSnapshots, snapshotBeforeInstall]);

  const handleBackupNow = useCallback(async () => {
    setBackupBusy(true);
    setBackupError(false);
    try {
      const current = status?.server_version ?? 'unknown';
      const target = latestVersion ?? 'manual';
      const response = await fetch('/api/v1/system/storage/snapshots/pre-update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ from_version: String(current), to_version: String(target) }),
      });
      if (!response.ok) {
        setBackupError(true);
      }
      await refreshSnapshots();
    } catch {
      setBackupError(true);
    } finally {
      setBackupBusy(false);
    }
  }, [latestVersion, refreshSnapshots, status?.server_version]);

  const handleRestore = useCallback(
    async (snapshotId: string) => {
      setBackupBusy(true);
      setBackupError(false);
      setRestoredId(null);
      try {
        const response = await fetch(`/api/v1/system/storage/snapshots/${snapshotId}/restore`, {
          method: 'POST',
        });
        if (!response.ok) {
          setBackupError(true);
          return;
        }
        setRestoredId(snapshotId);
      } catch {
        setBackupError(true);
      } finally {
        setBackupBusy(false);
      }
    },
    [],
  );

  const handleDeleteSnapshot = useCallback(
    async (snapshotId: string) => {
      try {
        await fetch(`/api/v1/system/storage/snapshots/${snapshotId}`, { method: 'DELETE' });
        await refreshSnapshots();
      } catch {
        // Best effort; the list refresh shows the truth.
        await refreshSnapshots();
      }
    },
    [refreshSnapshots],
  );

  const handleAutoBackupToggle = useCallback(() => {
    setAutoBackupState((enabled) => {
      const next = !enabled;
      setAutoBackup(next);
      return next;
    });
  }, []);

  const handleDefer = useCallback(() => {
    if (latestVersion) {
      setDeferredVersion(latestVersion);
      setDeferredVersionState(latestVersion);
    }
  }, [latestVersion]);

  const handleStartHourChange = useCallback((startVal: string) => {
    quietRef.current.start = startVal;
    setQuietStart(startVal);
    const currentEnd = quietRef.current.end;
    if (startVal === QUIET_OFF || currentEnd === QUIET_OFF) {
      setQuietHours(null);
      setQuiet(null);
      return;
    }
    const startHour = parseHour(startVal);
    const endHour = parseHour(currentEnd);
    if (startHour === null || endHour === null || startHour === endHour) {
      setQuietHours(null);
      setQuiet(null);
      return;
    }
    const hours = { startHour, endHour };
    setQuietHours(hours);
    setQuiet(hours);
  }, []);

  const handleEndHourChange = useCallback((endVal: string) => {
    quietRef.current.end = endVal;
    setQuietEnd(endVal);
    const currentStart = quietRef.current.start;
    if (currentStart === QUIET_OFF || endVal === QUIET_OFF) {
      setQuietHours(null);
      setQuiet(null);
      return;
    }
    const startHour = parseHour(currentStart);
    const endHour = parseHour(endVal);
    if (startHour === null || endHour === null || startHour === endHour) {
      setQuietHours(null);
      setQuiet(null);
      return;
    }
    const hours = { startHour, endHour };
    setQuietHours(hours);
    setQuiet(hours);
  }, []);

  const handleDoctor = useCallback(async () => {
    setDoctorResult(null);
    setIsDoctoring(true);
    try {
      const response = await fetch('/api/v1/health/update-status?force=true');
      if (!response.ok) {
        setDoctorResult('fail');
        return;
      }
      const payload = (await response.json()) as UpdateStatusPayload;
      setStatus(payload);
      setStatusError(false);
      setDoctorResult(payload.fetch_error ? 'fail' : 'pass');
    } catch {
      setDoctorResult('fail');
    } finally {
      setIsDoctoring(false);
    }
  }, []);

  const staleBadge = status?.stale === true && (isSecurity || (!deferred && !quietNow));

  return (
    <section className="space-y-6">
      <div className="flex items-center gap-3 px-2">
        <IconShield className="w-5 h-5 text-muted-foreground" />
        <h2 className="text-sm font-black uppercase tracking-[0.2em] text-muted-foreground/70">{t('title')}</h2>
      </div>

      <div className="space-y-6 p-8 rounded-[2.5rem] bg-white/5 border border-white/10">
        <div className="space-y-2">
          <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">{t('desktopTitle')}</p>
          {!isTauriRuntime() && <p className="text-xs text-muted-foreground">{t('desktopWebNote')}</p>}
          {isTauriRuntime() && desktopPhase === 'up_to_date' && (
            <p className="text-sm font-bold text-emerald-400">{t('desktopUpToDate')}</p>
          )}
          {isTauriRuntime() && desktopPhase === 'available' && (
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-sm font-bold text-foreground">
                {t('desktopAvailable', { version: desktopInfo?.version ?? '' })}
              </p>
              <button
                type="button"
                onClick={handleDesktopInstall}
                className="px-4 py-2 rounded-xl bg-indigo-500 text-white text-xs font-bold hover:bg-indigo-600 transition-colors"
              >
                {t('installNow')}
              </button>
            </div>
          )}
          {isTauriRuntime() && desktopPhase !== 'up_to_date' && desktopPhase !== 'available' && (
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-xs text-muted-foreground">
                {t('desktopState', { phase: desktopPhase })}
                {desktopPhase === 'downloading' && downloadProgress !== null && (
                  <span> · {downloadProgress}%</span>
                )}
              </p>
              {desktopPhase !== 'downloading' && desktopPhase !== 'installing' && desktopPhase !== 'restarting' && (
                <button
                  type="button"
                  onClick={() => void desktopCheck()}
                  className="px-3 py-1.5 rounded-lg border border-white/10 text-xs font-bold hover:bg-white/5 transition-colors"
                >
                  {t('checkNow')}
                </button>
              )}
            </div>
          )}
          {isTauriRuntime() && desktopError && (
            <p className="text-xs text-destructive/90">{desktopError}</p>
          )}
        </div>

        <div className="space-y-2">
          <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">{t('webTitle')}</p>
          {statusError && <p className="text-xs text-destructive/90">{t('webUnknown')}</p>}
          {status && (
            <div className="text-xs text-muted-foreground leading-relaxed">
              <p>
                {t('serverRow', { version: status.server_version ?? '?' })} ·{' '}
                {t('harnessRow', { version: status.harness_version ?? '?' })}
              </p>
              <p className="mt-1 flex flex-wrap items-center gap-2">
                {status.stale === true && (
                  <span className={cn('font-bold', staleBadge ? 'text-destructive' : 'text-muted-foreground')}>
                    {t('staleBadge', { version: latestVersion ?? '?' })}
                  </span>
                )}
                {status.stale !== true && <span className="font-bold text-emerald-400">{t('upToDateBadge')}</span>}
                {status.fetch_error && <span>· {t('unknownBadge')}</span>}
                {deferred && !isSecurity && <span>· {t('deferredHint', { version: deferredVersion ?? '' })}</span>}
              </p>
              {status.git && typeof status.git.behind_count === 'number' && status.git.behind_count > 0 && (
                <p className="mt-1">
                  {t('gitBehind', { count: status.git.behind_count })}
                  {status.git.log?.length ? ` — ${status.git.log[0]}` : ''}
                </p>
              )}
              {status.prebuilt && typeof status.prebuilt.synced_count === 'number' && (
                <p className="mt-1">{t('prebuiltSynced', { count: status.prebuilt.synced_count })}</p>
              )}
              <p className="mt-1">
                {t('cloudRow')}: {t('cloudUnknown')}
              </p>
            </div>
          )}
        </div>

        {(fixed.length > 0 || other.length > 0) && (
          <div className="space-y-3">
            {fixed.length > 0 && (
              <div>
                <p className="text-xs font-bold text-foreground mb-1">{t('changelogFixed')}</p>
                <ul className="space-y-1">
                  {visibleFixed.map((item, index) => (
                    <li key={index} className="text-xs text-muted-foreground flex items-start gap-2">
                      <span className="text-emerald-400 mt-0.5">•</span>
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {other.length > 0 && (
              <div>
                <p className="text-xs font-bold text-foreground mb-1">{t('changelogOther')}</p>
                <ul className="space-y-1">
                  {visibleOther.map((item, index) => (
                    <li key={index} className="text-xs text-muted-foreground flex items-start gap-2">
                      <span className="text-primary mt-0.5">•</span>
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {(fixed.length > 5 || other.length > 5) && (
              <button
                type="button"
                onClick={() => setExpanded((value) => !value)}
                className="text-xs font-bold text-primary hover:underline"
              >
                {expanded ? t('showLess') : t('showMore')}
              </button>
            )}
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          {latestVersion && !deferred && !isSecurity && (
            <button
              type="button"
              onClick={handleDefer}
              className="px-4 py-2 rounded-xl border border-white/10 text-xs font-bold hover:bg-white/5 transition-colors"
            >
              {t('defer', { version: latestVersion })}
            </button>
          )}
          {latestVersion && isSecurity && (
            <div className="px-4 py-2 rounded-xl border border-amber-500/20 bg-amber-500/10 text-amber-400 text-xs font-bold flex items-center gap-1.5">
              <IconShield className="w-3.5 h-3.5 shrink-0" />
              <span>{t('securityPatch')}</span>
            </div>
          )}
          <button
            type="button"
            onClick={handleDoctor}
            disabled={isDoctoring}
            className={cn(
              "px-4 py-2 rounded-xl border border-white/10 text-xs font-bold transition-colors",
              isDoctoring ? "opacity-60 cursor-not-allowed" : "hover:bg-white/5"
            )}
          >
            {isDoctoring ? `${t('doctorRun')}...` : t('doctorRun')}
          </button>
          {doctorResult === 'pass' && (
            <p className="text-xs text-emerald-400 self-center">{t('doctorPass')}</p>
          )}
          {doctorResult === 'fail' && (
            <p className="text-xs text-destructive self-center">{t('doctorFail')}</p>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span>{t('quietTitle')}</span>
          <select
            aria-label={t('quietTitle')}
            value={quietStart}
            onChange={(event) => handleStartHourChange(event.target.value)}
            className="px-2 py-1 rounded-lg border border-white/10 bg-transparent text-xs"
          >
            <option value={QUIET_OFF}>{t('quietOff')}</option>
            {Array.from({ length: 24 }, (_, hour) => (
              <option key={hour} value={String(hour)}>
                {String(hour).padStart(2, '0')}:00
              </option>
            ))}
          </select>
          <span>→</span>
          <select
            aria-label={t('quietTitle')}
            value={quietEnd}
            onChange={(event) => handleEndHourChange(event.target.value)}
            className="px-2 py-1 rounded-lg border border-white/10 bg-transparent text-xs"
          >
            <option value={QUIET_OFF}>{t('quietOff')}</option>
            {Array.from({ length: 24 }, (_, hour) => (
              <option key={hour} value={String(hour)}>
                {String(hour).padStart(2, '0')}:00
              </option>
            ))}
          </select>
          {quietNow && <span>{t('quietActive')}</span>}
        </div>
      </div>
    </section>
  );
}
