'use client';

import { memo, useCallback, useEffect, useState } from 'react';
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
import { IconGlobe, IconRefresh, IconTrash } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Switch } from '@/components/primitives/switch';
import { cn } from '@/lib/utils/classnameUtils';

interface DoctorCheck {
  status: string;
  message: string;
  fix?: string | null;
  details?: Record<string, unknown>;
}

interface BrowserDoctorReport {
  summary: string;
  overall_healthy: boolean;
  checks: Record<string, DoctorCheck>;
  recommendations: string[];
}

interface OrphanCleanupResult {
  killed?: number;
  dry_run?: boolean;
  message?: string;
}

const STATUS_COLOR: Record<string, string> = {
  ok: 'text-emerald-500',
  warning: 'text-amber-500',
  error: 'text-red-500',
  missing: 'text-red-500',
};

const STATUS_KEYS: Record<string, string> = {
  ok: 'statusOk',
  warning: 'statusWarning',
  error: 'statusError',
  missing: 'statusMissing',
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

  const fetchDoctor = useCallback(async (includeLaunchTest: boolean) => {
    setLoading(true);
    setError(null);
    try {
      const qs = includeLaunchTest ? '?launch_test=true' : '?launch_test=false';
      const resp = await fetch(`/api/v1/health/browser/doctor${qs}`);
      if (!resp.ok) {
        throw new Error(await resp.text());
      }
      setReport(await resp.json());
    } catch (err) {
      setReport(null);
      setError(err instanceof Error ? err.message : t('loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void fetchDoctor(true);
  }, [fetchDoctor]);

  const cleanupOrphans = useCallback(async () => {
    setCleaning(true);
    setCleanupError(null);
    try {
      const resp = await fetch('/api/v1/health/browser/orphans?confirm=true', {
        method: 'DELETE',
      });
      if (!resp.ok) {
        throw new Error(await resp.text());
      }
      const data = (await resp.json()) as OrphanCleanupResult;
      setCleanupMessage(t('cleaned', { count: data.killed ?? 0 }));
      setCleanupOpen(false);
      await fetchDoctor(launchTest);
    } catch (err) {
      setCleanupError(err instanceof Error ? err.message : t('cleanupFailed'));
    } finally {
      setCleaning(false);
    }
  }, [fetchDoctor, launchTest, t]);

  const healthy = report?.overall_healthy ?? false;
  const orphanCheck = report?.checks?.orphan_processes;
  const hasOrphans = orphanCheck !== undefined && orphanCheck.status !== 'ok';
  const orphanCount =
    typeof orphanCheck?.details?.count === 'number' ? orphanCheck.details.count : 0;

  return (
    <section className="space-y-4">
      <div className="flex flex-col gap-3 px-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <IconGlobe className="h-5 w-5 shrink-0 text-muted-foreground" />
          <h2 className="text-sm font-black uppercase tracking-[0.2em] text-muted-foreground/70">{t('title')}</h2>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={loading}
            onClick={() => void fetchDoctor(launchTest)}
            className="gap-2"
          >
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
          <Switch
            id="browser-doctor-launch-test"
            checked={launchTest}
            onCheckedChange={setLaunchTest}
          />
        </div>

        {error && <p className="text-sm text-red-400">{error}</p>}

        {report && !error && (
          <>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-sm font-medium">{report.summary}</p>
              <span
                className={cn(
                  'inline-flex w-fit rounded-full px-2.5 py-0.5 text-xs font-bold uppercase',
                  healthy ? 'bg-emerald-500/10 text-emerald-500' : 'bg-amber-500/10 text-amber-500',
                )}
              >
                {healthy ? t('healthy') : t('unhealthy')}
              </span>
            </div>

            {report.recommendations.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t('recommendations')}</p>
                <ul className="list-disc space-y-1 pl-4 text-xs text-muted-foreground">
                  {report.recommendations.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            )}

            <div className="space-y-2">
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t('checks')}</p>
              <div className="max-h-72 space-y-2 overflow-y-auto">
                {Object.entries(report.checks).map(([name, check]) => (
                  <div key={name} className="rounded-lg border border-white/5 bg-background/40 p-3 text-xs">
                    <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                      <span className="break-all font-medium">
                        {(KNOWN_CHECK_NAMES as readonly string[]).includes(name)
                          ? t(`checkNames.${name}`)
                          : name}
                      </span>
                      <span className={cn('font-bold uppercase', STATUS_COLOR[check.status] ?? 'text-muted-foreground')}>
                        {t(STATUS_KEYS[check.status] ?? check.status)}
                      </span>
                    </div>
                    <p className="mt-1 text-muted-foreground">{check.message}</p>
                    {check.fix && !(name === 'orphan_processes' && hasOrphans) && (
                      <p className="mt-1 text-indigo-400/90">
                        {t('fix')}: {check.fix}
                      </p>
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
                    {name === 'orphan_processes' && cleanupMessage && (
                      <p className="mt-1 text-emerald-400/90">{cleanupMessage}</p>
                    )}
                    {name === 'orphan_processes' && cleanupError && (
                      <p className="mt-1 text-red-400">{cleanupError}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>

      <AlertDialog open={cleanupOpen} onOpenChange={setCleanupOpen}>
        <AlertDialogContent className="max-w-md">
          <AlertDialogHeader>
            <AlertDialogTitle>{t('confirmCleanupTitle')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('confirmCleanupDescription', { count: orphanCount })}
            </AlertDialogDescription>
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
