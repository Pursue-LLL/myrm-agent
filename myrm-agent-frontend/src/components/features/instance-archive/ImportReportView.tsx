'use client';

/**
 * [INPUT]
 * - @/services/instanceArchive: ImportReport
 * - @/lib/instance-archive/{counts,format,reentry}: count keys, history-loss check, date label, credential groups
 * - next-intl::useLocale (POS: app language for dates and numbers)
 *
 * [OUTPUT]
 * - ImportReportView: what a verified backup contains next to what the app holds now
 *
 * [POS]
 * Review step of the import wizard; the user sees when the backup was made and what restoring
 * replaces, then confirms (and, for executable content, acknowledges trust) from here.
 */

import { memo, useMemo, type ReactNode } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { CheckCircle, Info, Terminal, WarningCircle } from '@phosphor-icons/react';
import { Checkbox } from '@/components/primitives/checkbox';
import { COUNT_KEYS, losesHistory } from '@/lib/instance-archive/counts';
import { formatBackupDate } from '@/lib/instance-archive/format';
import { reentryGroups } from '@/lib/instance-archive/reentry';
import { cn } from '@/lib/utils/classnameUtils';
import type { ImportReport } from '@/services/instanceArchive';

interface ImportReportViewProps {
  report: ImportReport;
  acknowledged: boolean;
  onAcknowledgedChange: (value: boolean) => void;
}

const EXECUTABLE_ORDER = ['scheduled_commands', 'mcp_stdio_servers', 'skill_scripts'] as const;

export function hasExecutableContent(report: ImportReport): boolean {
  return Object.values(report.executable).some((count) => count > 0);
}

function WarningNote({ children }: { children: ReactNode }) {
  return (
    <p className="flex items-start gap-2 rounded-xl border border-amber-500/40 bg-amber-500/10 p-3 text-xs font-medium leading-relaxed text-amber-700 dark:text-amber-300">
      <WarningCircle className="mt-0.5 h-4 w-4 shrink-0" weight="fill" />
      {children}
    </p>
  );
}

export const ImportReportView = memo(function ImportReportView({
  report,
  acknowledged,
  onAcknowledgedChange,
}: ImportReportViewProps) {
  const t = useTranslations('instanceArchive.report');
  const tGroup = useTranslations('instanceArchive.groups');
  const locale = useLocale();
  const madeAt = formatBackupDate(report.created_at, locale);
  const groups = useMemo(() => reentryGroups(report.reentry), [report.reentry]);
  const executable = EXECUTABLE_ORDER.filter((key) => (report.executable[key] ?? 0) > 0);

  const notes: string[] = [];
  if (report.paused_jobs > 0) {
    notes.push(t('pausedJobs', { count: report.paused_jobs }));
  }
  if (report.missing_paths > 0) {
    notes.push(t('missingPaths', { count: report.missing_paths }));
  }
  if (report.identity_dropped) {
    notes.push(t('identityDropped'));
  }
  if (report.config_key_carried) {
    notes.push(t('keysCarried'));
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-sm font-semibold text-emerald-600 dark:text-emerald-400">
        <CheckCircle className="h-4 w-4" weight="fill" />
        {t('verified')}
      </div>

      {madeAt && <p className="text-xs text-muted-foreground">{t('madeAt', { date: madeAt })}</p>}

      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {COUNT_KEYS.filter((key) => key in report.counts).map((key) => {
          const current = report.current_counts[key];
          const fewer = current !== undefined && report.counts[key] < current;
          return (
            <div key={key} className="flex flex-col rounded-xl border border-border/50 bg-muted/20 px-3 py-2">
              <dt className="order-2 text-xs text-muted-foreground">{t(`counts.${key}`)}</dt>
              <dd className="order-1 text-lg font-black tracking-tight text-foreground">
                {report.counts[key].toLocaleString(locale)}
              </dd>
              {current !== undefined && (
                <dd
                  className={cn(
                    'order-3 mt-1 text-[11px]',
                    fewer ? 'font-semibold text-amber-700 dark:text-amber-300' : 'text-muted-foreground',
                  )}
                >
                  {t('nowCount', { count: current.toLocaleString(locale) })}
                </dd>
              )}
            </div>
          );
        })}
      </dl>

      {losesHistory(report) && <WarningNote>{t('losesHistory')}</WarningNote>}

      {report.unreadable_count > 0 && <WarningNote>{t('incomplete', { count: report.unreadable_count })}</WarningNote>}

      <p className="flex items-start gap-2 text-xs leading-relaxed text-muted-foreground">
        <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" weight="bold" />
        {t('replaceWarning')}
      </p>

      {notes.length > 0 && (
        <ul className="list-inside list-disc space-y-1 text-xs leading-relaxed text-muted-foreground">
          {notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}

      {groups.length > 0 && (
        <div className="space-y-1 text-xs text-muted-foreground">
          <p className="font-semibold text-foreground">{t('reentryTitle')}</p>
          <ul className="list-inside list-disc space-y-0.5">
            {groups.map((group) => (
              <li key={group}>{tGroup(group)}</li>
            ))}
          </ul>
        </div>
      )}

      {executable.length > 0 && (
        <div className="space-y-3 rounded-xl border border-amber-500/40 bg-amber-500/10 p-3">
          <p className="flex items-center gap-2 text-xs font-semibold text-amber-700 dark:text-amber-300">
            <Terminal className="h-4 w-4" weight="bold" />
            {t('executableTitle')}
          </p>
          <ul className="list-inside list-disc space-y-0.5 text-xs text-muted-foreground">
            {executable.map((key) => (
              <li key={key}>{t(`executable.${key}`, { count: report.executable[key] })}</li>
            ))}
          </ul>
          <label className="flex cursor-pointer items-center gap-2 text-xs font-medium text-foreground">
            <Checkbox
              checked={acknowledged}
              onCheckedChange={(value) => onAcknowledgedChange(value === true)}
              aria-label={t('trust')}
            />
            {t('trust')}
          </label>
        </div>
      )}
    </div>
  );
});
