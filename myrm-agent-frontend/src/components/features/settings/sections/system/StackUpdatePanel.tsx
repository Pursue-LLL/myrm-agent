'use client';

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconCheck, IconShield } from '@/components/features/icons/PremiumIcons';
import { isTauriRuntime } from '@/lib/deploy-mode';
import { useAppUpdate } from '@/hooks/tauri/useAppUpdate';
import {
  getDeferredVersion,
  getQuietHours,
  isDeferred,
  isQuietNow,
  saveUpdateReceipt,
  setDeferredVersion,
  setQuietHours,
  takeUpdateReceipt,
  type QuietHours,
  type UpdateReceipt,
} from '@/lib/update-prefs';
import { cn } from '@/lib/utils/classnameUtils';

interface ChangelogGroups {
  fixed: string[];
  other: string[];
  grouped: boolean;
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

const StackUpdatePanel = memo(() => {
  const t = useTranslations('settings.system.stackUpdate');
  const [status, setStatus] = useState<UpdateStatusPayload | null>(null);
  const [statusError, setStatusError] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [deferredVersion, setDeferredVersionState] = useState<string | null>(null);
  const [quiet, setQuiet] = useState<QuietHours | null>(null);
  const [receipt, setReceipt] = useState<UpdateReceipt | null>(null);
  const [doctorResult, setDoctorResult] = useState<'pass' | 'fail' | null>(null);

  const {
    phase: desktopPhase,
    info: desktopInfo,
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

  useEffect(() => {
    setDeferredVersionState(getDeferredVersion());
    setQuiet(getQuietHours());
    setReceipt(takeUpdateReceipt());
    void refreshStatus();
  }, [refreshStatus]);

  const latestVersion = status?.latest?.version ?? null;
  const deferred = isDeferred(latestVersion);
  const quietNow = isQuietNow(quiet);
  const fixed = status?.changelog?.fixed ?? [];
  const other = status?.changelog?.other ?? [];
  const visibleFixed = expanded ? fixed : fixed.slice(0, 5);
  const visibleOther = expanded ? other : other.slice(0, 5);

  const handleDesktopInstall = useCallback(() => {
    if (desktopInfo) {
      saveUpdateReceipt({
        fromVersion: desktopInfo.currentVersion,
        toVersion: desktopInfo.version,
        at: new Date().toISOString(),
      });
    }
    void desktopInstall();
  }, [desktopInfo, desktopInstall]);

  const handleDefer = useCallback(() => {
    if (latestVersion) {
      setDeferredVersion(latestVersion);
      setDeferredVersionState(latestVersion);
    }
  }, [latestVersion]);

  const handleQuietChange = useCallback((start: string, end: string) => {
    if (start === QUIET_OFF || end === QUIET_OFF) {
      setQuietHours(null);
      setQuiet(null);
      return;
    }
    const startHour = parseHour(start);
    const endHour = parseHour(end);
    if (startHour === null || endHour === null || startHour === endHour) {
      return;
    }
    const hours = { startHour, endHour };
    setQuietHours(hours);
    setQuiet(hours);
  }, []);

  const handleDoctor = useCallback(async () => {
    setDoctorResult(null);
    try {
      const response = await fetch('/api/v1/health/update-status');
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
    }
  }, []);

  const staleBadge = status?.stale === true && !deferred && !quietNow;

  return (
    <section className="space-y-6">
      <div className="flex items-center gap-3 px-2">
        <IconShield className="w-5 h-5 text-muted-foreground" />
        <h2 className="text-sm font-black uppercase tracking-[0.2em] text-muted-foreground/70">{t('title')}</h2>
      </div>

      <div className="space-y-6 p-8 rounded-[2.5rem] bg-white/5 border border-white/10">
        {receipt && (
          <div className="flex items-start gap-2 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 p-3">
            <IconCheck className="w-4 h-4 mt-0.5 shrink-0 text-emerald-400" />
            <p className="text-xs text-emerald-200/90 leading-relaxed">
              {t('receipt', { from: receipt.fromVersion, to: receipt.toVersion })}
            </p>
          </div>
        )}

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
              <p className="text-xs text-muted-foreground">{t('desktopState', { phase: desktopPhase })}</p>
              <button
                type="button"
                onClick={() => void desktopCheck()}
                className="px-3 py-1.5 rounded-lg border border-white/10 text-xs font-bold hover:bg-white/5 transition-colors"
              >
                {t('checkNow')}
              </button>
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
                {deferred && <span>· {t('deferredHint', { version: deferredVersion ?? '' })}</span>}
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
          {latestVersion && !deferred && (
            <button
              type="button"
              onClick={handleDefer}
              className="px-4 py-2 rounded-xl border border-white/10 text-xs font-bold hover:bg-white/5 transition-colors"
            >
              {t('defer', { version: latestVersion })}
            </button>
          )}
          <button
            type="button"
            onClick={handleDoctor}
            className="px-4 py-2 rounded-xl border border-white/10 text-xs font-bold hover:bg-white/5 transition-colors"
          >
            {t('doctorRun')}
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
            value={quiet ? String(quiet.startHour) : QUIET_OFF}
            onChange={(event) =>
              handleQuietChange(event.target.value, quiet ? String(quiet.endHour) : QUIET_OFF)
            }
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
            value={quiet ? String(quiet.endHour) : QUIET_OFF}
            onChange={(event) =>
              handleQuietChange(quiet ? String(quiet.startHour) : QUIET_OFF, event.target.value)
            }
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
});

StackUpdatePanel.displayName = 'StackUpdatePanel';
export default StackUpdatePanel;
