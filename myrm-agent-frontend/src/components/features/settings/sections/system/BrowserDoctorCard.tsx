'use client';

/**
 * Browser diagnostics card: runs the doctor, shows a plain-language summary and cleans orphaned automation leftovers.
 *
 * [INPUT]
 * - `GET /api/v1/health/browser/doctor` (optional launch test) and `DELETE /api/v1/health/browser/orphans?confirm=true`
 * - ./browserDoctorView::buildDoctorView/statusLabelKey (POS: tone, localized hint and counts of a report)
 *
 * [OUTPUT]
 * - default export BrowserDoctorCard: settings card for the browser stack health
 *
 * [POS]
 * 系统设置页的浏览器栈诊断入口：头条与徽标只呈现「需关注项」，英文 message/fix 收进可展开的技术详情；
 * 孤儿进程与过期沙箱经二次确认后清理。
 */

import { memo, useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/primitives/alert-dialog';
import {
  IconChevronDown,
  IconChevronUp,
  IconGlobe,
  IconRefresh,
  IconTrash,
} from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { apiRequest } from '@/lib/api';
import { Switch } from '@/components/primitives/switch';
import { cn } from '@/lib/utils/classnameUtils';
import { buildDoctorView, statusLabelKey, type BrowserDoctorReport, type DoctorTone } from './browserDoctorView';

interface OrphanCleanupFailed {
  pid: number;
  reason: string;
}

interface OrphanCleanupResult {
  killed?: number;
  sandboxes_pruned?: number;
  reclaimed_bytes?: number;
  dry_run?: boolean;
  message?: string;
  failed?: OrphanCleanupFailed[];
}

function formatBytes(bytes: number): string {
  if (bytes <= 0) {
    return '0 B';
  }
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / Math.pow(1024, i);
  return `${value.toFixed(value >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
}

// Light/dark pairs keep status text at WCAG AA contrast on both card backgrounds.
const TEXT_OK = 'text-emerald-700 dark:text-emerald-400';
const TEXT_ATTENTION = 'text-amber-700 dark:text-amber-400';
const TEXT_ERROR = 'text-red-600 dark:text-red-400';

const TONE_COLOR: Record<DoctorTone, string> = {
  ok: TEXT_OK,
  optional: 'text-muted-foreground',
  attention: TEXT_ATTENTION,
  error: TEXT_ERROR,
};

const KNOWN_CHECK_NAMES = [
  'patchright',
  'camoufox',
  'memory',
  'disk',
  'proxy',
  'orphan_processes',
  'browser_launch',
  'extension_relay',
] as const;

/**
 * Extract a user-readable message from a non-OK API response.
 * Server errors come in two shapes: FastAPI uses `{"detail": ...}` (string or
 * validation array), the global exception handler uses `{success, message}`.
 * Falls back to the raw body when it is not JSON, and to `fallback` when empty.
 */
async function readApiErrorDetail(resp: Response, fallback: string): Promise<string> {
  const raw = await resp.text();
  if (!raw) {
    return fallback;
  }
  try {
    const body = JSON.parse(raw) as {
      detail?: unknown;
      message?: unknown;
    };
    const detail = body.detail;
    if (typeof detail === 'string' && detail.trim()) {
      return detail;
    }
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: unknown };
      if (typeof first?.msg === 'string' && first.msg.trim()) {
        return first.msg;
      }
    }
    if (typeof body.message === 'string' && body.message.trim()) {
      return body.message;
    }
  } catch {
    // Non-JSON body, fall through to raw text below.
  }
  return raw.trim() || fallback;
}

const BrowserDoctorCard = memo(() => {
  const t = useTranslations('settings.browserDoctor');
  const [report, setReport] = useState<BrowserDoctorReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [launchTest, setLaunchTest] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [cleanupOpen, setCleanupOpen] = useState(false);
  const [cleaning, setCleaning] = useState(false);
  const [cleanupError, setCleanupError] = useState<string | null>(null);
  const [cleanupMessage, setCleanupMessage] = useState<string | null>(null);
  const [cleanupHasFailures, setCleanupHasFailures] = useState(false);
  // null follows the default: technical details open by default only while something has failed.
  const [technicalOverride, setTechnicalOverride] = useState<boolean | null>(null);

  const fetchDoctor = useCallback(
    async (includeLaunchTest: boolean) => {
      setLoading(true);
      setError(null);
      try {
        const qs = includeLaunchTest ? '?launch_test=true' : '?launch_test=false';
        const resp = await fetch(`/api/v1/health/browser/doctor${qs}`);
        if (!resp.ok) {
          throw new Error(await readApiErrorDetail(resp, t('loadFailed')));
        }
        setReport(await resp.json());
      } catch (err) {
        setReport(null);
        setError(err instanceof Error ? err.message : t('loadFailed'));
      } finally {
        setLoading(false);
      }
    },
    [t],
  );

  const runDiagnosis = useCallback(() => {
    setCleanupMessage(null);
    setCleanupError(null);
    setCleanupHasFailures(false);
    void fetchDoctor(launchTest);
  }, [fetchDoctor, launchTest]);

  useEffect(() => {
    void fetchDoctor(true);
  }, [fetchDoctor]);

  const cleanupOrphans = useCallback(async () => {
    setCleaning(true);
    setCleanupError(null);
    setCleanupMessage(null);
    setCleanupHasFailures(false);
    try {
      const data = await apiRequest<OrphanCleanupResult>('/health/browser/orphans?confirm=true', {
        method: 'DELETE',
        silent: true,
      });
      const failed = data.failed ?? [];
      if (failed.length > 0) {
        setCleanupHasFailures(true);
        setCleanupMessage(t('cleanupPartial', { failed: failed.length }));
      } else {
        setCleanupHasFailures(false);
        const reclaimed = data.reclaimed_bytes ?? 0;
        if (reclaimed > 0) {
          const killedCount = data.killed ?? 0;
          if (killedCount > 0) {
            setCleanupMessage(
              t('cleanedWithReclaimed', {
                count: killedCount,
                size: formatBytes(reclaimed),
              }),
            );
          } else {
            setCleanupMessage(
              t('reclaimedOnly', {
                size: formatBytes(reclaimed),
              }),
            );
          }
        } else {
          setCleanupMessage(t('cleaned', { count: data.killed ?? 0 }));
        }
      }
      setCleanupOpen(false);
      await fetchDoctor(launchTest);
    } catch (err) {
      setCleanupOpen(false);
      setCleanupError(err instanceof Error ? err.message : t('cleanupFailed'));
    } finally {
      setCleaning(false);
    }
  }, [fetchDoctor, launchTest, t]);

  const view = useMemo(() => (report ? buildDoctorView(report) : null), [report]);
  const technicalOpen = technicalOverride ?? view?.hasFailure ?? false;
  const orphanCheck = report?.checks?.orphan_processes;
  const staleSandboxes =
    typeof orphanCheck?.details?.stale_sandboxes === 'number' ? orphanCheck.details.stale_sandboxes : 0;
  const orphanCount = typeof orphanCheck?.details?.count === 'number' ? orphanCheck.details.count : 0;
  const hasOrphans =
    (orphanCheck !== undefined && orphanCheck.status !== 'ok') || orphanCount > 0 || staleSandboxes > 0;

  return (
    <section className="space-y-4">
      <div className="flex flex-col gap-3 px-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <IconGlobe className="h-5 w-5 shrink-0 text-muted-foreground" />
          <h2 className="text-sm font-black uppercase tracking-[0.2em] text-muted-foreground/70">{t('title')}</h2>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="outline" size="sm" disabled={loading} onClick={runDiagnosis} className="gap-2">
            <IconRefresh className={cn('h-3.5 w-3.5', loading && 'animate-spin')} />
            {loading ? t('running') : t('runCheck')}
          </Button>
        </div>
      </div>

      <div className="space-y-4 rounded-2xl border border-white/5 bg-card/50 p-4 sm:p-5">
        <p className="text-xs leading-relaxed text-muted-foreground">{t('description')}</p>

        <div className="flex flex-col gap-3 rounded-xl border border-white/5 bg-background/30 p-3 sm:flex-row sm:items-center sm:justify-between">
          <label htmlFor="browser-doctor-launch-test" className="text-sm text-foreground">
            {t('launchTest')}
          </label>
          <Switch id="browser-doctor-launch-test" checked={launchTest} onCheckedChange={setLaunchTest} />
        </div>

        {error && (
          <p role="alert" className={cn('text-sm', TEXT_ERROR)}>
            {error}
          </p>
        )}

        {report && view && !error && (
          <>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div className="space-y-0.5">
                <p className="text-sm font-medium">
                  {view.needsAttention > 0
                    ? t('summaryNeedsAttention', { count: view.needsAttention })
                    : t('summaryAllClear')}
                </p>
                {view.optionalCount > 0 && (
                  <p className="text-xs text-muted-foreground">{t('summaryOptional', { count: view.optionalCount })}</p>
                )}
              </div>
              <span
                className={cn(
                  'inline-flex w-fit rounded-full px-2.5 py-0.5 text-xs font-bold uppercase',
                  view.healthy ? 'bg-emerald-500/10' : 'bg-amber-500/10',
                  view.healthy ? TEXT_OK : TEXT_ATTENTION,
                )}
              >
                {view.healthy ? t('healthy') : t('unhealthy')}
              </span>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t('checks')}</p>
                <button
                  type="button"
                  aria-expanded={technicalOpen}
                  onClick={() => setTechnicalOverride(!technicalOpen)}
                  className="inline-flex items-center gap-1 rounded text-xs font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  {t('technicalDetails')}
                  {technicalOpen ? (
                    <IconChevronUp className="h-3.5 w-3.5" />
                  ) : (
                    <IconChevronDown className="h-3.5 w-3.5" />
                  )}
                </button>
              </div>
              <div className="space-y-2">
                {view.rows.map(({ name, check, tone, hint }) => (
                  <div key={name} className="rounded-lg border border-border/60 bg-background/40 p-3 text-xs">
                    <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                      <span className="break-all font-medium">
                        {(KNOWN_CHECK_NAMES as readonly string[]).includes(name) ? t(`checkNames.${name}`) : name}
                      </span>
                      <span className={cn('font-bold uppercase', TONE_COLOR[tone])}>
                        {t(statusLabelKey(tone, check.status))}
                      </span>
                    </div>
                    {hint && <p className="mt-1 text-muted-foreground">{t(hint.key, hint.values)}</p>}
                    {technicalOpen && (
                      <div className="mt-2 space-y-1 rounded-md bg-muted/50 p-2 font-mono text-[11px] leading-relaxed text-muted-foreground">
                        <p className="break-words">{check.message}</p>
                        {check.fix && !(name === 'orphan_processes' && hasOrphans) && (
                          <p className="break-words text-indigo-600 dark:text-indigo-400">
                            {t('fix')}: {check.fix}
                          </p>
                        )}
                      </div>
                    )}
                    {name === 'orphan_processes' && hasOrphans && (
                      <div className="mt-2">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          disabled={cleaning}
                          onClick={() => setCleanupOpen(true)}
                          className="gap-1.5"
                        >
                          <IconTrash className="h-3.5 w-3.5" />
                          {cleaning ? t('cleaning') : t('cleanupOrphans')}
                        </Button>
                      </div>
                    )}
                    {name === 'orphan_processes' && (
                      // The region is always mounted so screen readers announce text that is added later.
                      <output className="block">
                        {cleanupMessage && (
                          <p className={cn('mt-1', cleanupHasFailures ? TEXT_ATTENTION : TEXT_OK)}>{cleanupMessage}</p>
                        )}
                        {cleanupError && <p className={cn('mt-1', TEXT_ERROR)}>{cleanupError}</p>}
                      </output>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {technicalOpen && report.recommendations.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  {t('recommendations')}
                </p>
                <ul className="list-disc space-y-1 pl-4 font-mono text-[11px] text-muted-foreground">
                  {report.recommendations.map((item) => (
                    <li key={item} className="break-words">
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </div>

      <AlertDialog open={cleanupOpen} onOpenChange={setCleanupOpen}>
        <AlertDialogContent className="max-w-md">
          <AlertDialogHeader>
            <AlertDialogTitle>{t('confirmCleanupTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('confirmCleanupDescription')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={cleaning}>{t('cancel')}</AlertDialogCancel>
            <AlertDialogAction
              disabled={cleaning}
              onClick={() => void cleanupOrphans()}
              className="bg-red-500 hover:bg-red-600 focus-visible:ring-red-500/40"
            >
              {cleaning ? t('cleaning') : t('cleanupOrphans')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  );
});

BrowserDoctorCard.displayName = 'BrowserDoctorCard';

export default BrowserDoctorCard;
