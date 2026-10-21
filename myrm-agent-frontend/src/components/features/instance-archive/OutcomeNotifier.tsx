'use client';

/**
 * [INPUT]
 * - @/services/instanceArchive: one-time swap outcome, rollback, status
 * - @/lib/instance-archive/{counts,reentry}: count keys, credential groups
 * - next-intl::useTranslations('instanceArchive'), useLocale (number formatting)
 *
 * [OUTPUT]
 * - OutcomeNotifier: dialog shown once after a restore / import / undo was applied during boot
 *
 * [POS]
 * Mounted app-wide (DeferredAppInitializers): the user restarts from wherever they are, so
 * the result, the credentials to enter again and the undo action must meet them on return.
 */

import { memo, useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useLocale, useTranslations } from 'next-intl';
import { ArrowCounterClockwise, CheckCircle, CircleNotch, WarningCircle } from '@phosphor-icons/react';
import { Button } from '@/components/primitives/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import { COUNT_KEYS } from '@/lib/instance-archive/counts';
import { reentryGroups, type ReentryGroup } from '@/lib/instance-archive/reentry';
import {
  archiveErrorCode,
  instanceArchiveService,
  type ArchiveOperation,
  type ArchiveOutcome,
  type RestartMode,
} from '@/services/instanceArchive';
import { ArchiveErrorNotice } from './ArchiveErrorNotice';
import { RestartNotice } from './RestartNotice';

const SETTINGS_HREF: Readonly<Record<ReentryGroup, string>> = {
  modelKeys: '/settings/models',
  mcpConnections: '/settings/mcp',
  savedSecrets: '/settings/credentials',
  connectedAccounts: '/settings/channels',
};

const TITLE_KEY: Readonly<Record<ArchiveOperation, 'restoredImport' | 'restoredPoint' | 'restoredRollback'>> = {
  import: 'restoredImport',
  restore_point: 'restoredPoint',
  rollback: 'restoredRollback',
};

export const OutcomeNotifier = memo(function OutcomeNotifier() {
  const t = useTranslations('instanceArchive.outcome');
  const tCounts = useTranslations('instanceArchive.report.counts');
  const tGroup = useTranslations('instanceArchive.groups');
  const locale = useLocale();
  const [outcome, setOutcome] = useState<ArchiveOutcome | null>(null);
  const [undoing, setUndoing] = useState(false);
  const [undoError, setUndoError] = useState<string | null>(null);
  const [restartMode, setRestartMode] = useState<RestartMode | null>(null);

  useEffect(() => {
    let cancelled = false;
    instanceArchiveService
      .getOutcome()
      .then((found) => {
        if (!cancelled && found && found.status !== 'waiting') {
          setOutcome(found);
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  const dismiss = useCallback(() => {
    setOutcome(null);
    void instanceArchiveService.acknowledgeOutcome().catch(() => undefined);
  }, []);

  const undo = useCallback(async () => {
    setUndoing(true);
    setUndoError(null);
    try {
      await instanceArchiveService.queueRollback();
      setRestartMode((await instanceArchiveService.getStatus()).restart_mode);
    } catch (error) {
      setUndoError(archiveErrorCode(error));
    } finally {
      setUndoing(false);
    }
  }, []);

  if (!outcome) {
    return null;
  }

  const restored = outcome.status === 'restored';
  const counts = COUNT_KEYS.filter((key) => (outcome.summary[key] ?? 0) > 0);
  const groups = reentryGroups(outcome.reentry);

  return (
    <Dialog open onOpenChange={(open) => !open && dismiss()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle className={restored ? 'flex items-center gap-2' : 'flex items-center gap-2 text-destructive'}>
            {restored ? (
              <CheckCircle className="h-5 w-5 text-emerald-600 dark:text-emerald-400" weight="fill" />
            ) : (
              <WarningCircle className="h-5 w-5" weight="fill" />
            )}
            {restored ? t(TITLE_KEY[outcome.operation]) : t('failedTitle')}
          </DialogTitle>
          <DialogDescription>
            {restored
              ? t(outcome.operation === 'rollback' ? 'rollbackDescription' : 'restoredDescription')
              : t('failedDescription')}
          </DialogDescription>
        </DialogHeader>

        {!restored && <ArchiveErrorNotice code={outcome.error_code ?? 'restore_failed'} />}

        {restored && counts.length > 0 && (
          <dl className="grid grid-cols-2 gap-2">
            {counts.map((key) => (
              <div key={key} className="flex flex-col rounded-xl border border-border/50 bg-muted/20 px-3 py-2">
                <dt className="order-2 text-xs text-muted-foreground">{tCounts(key)}</dt>
                <dd className="order-1 text-base font-black tracking-tight text-foreground">
                  {outcome.summary[key].toLocaleString(locale)}
                </dd>
              </div>
            ))}
          </dl>
        )}

        {restored && groups.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs font-semibold text-foreground">{t('reentryTitle')}</p>
            <ul className="space-y-1.5">
              {groups.map((group) => (
                <li key={group} className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
                  <span>{tGroup(group)}</span>
                  <Link
                    href={SETTINGS_HREF[group]}
                    onClick={dismiss}
                    className="shrink-0 font-semibold text-primary hover:underline"
                  >
                    {t('open')}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        )}

        {undoError && <ArchiveErrorNotice code={undoError} />}
        {restartMode && <RestartNotice mode={restartMode} />}

        <DialogFooter className="gap-2 sm:gap-0">
          {restored && outcome.rollback_available && !restartMode && (
            <Button variant="outline" className="gap-1.5 rounded-xl" disabled={undoing} onClick={() => void undo()}>
              {undoing ? (
                <CircleNotch className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <ArrowCounterClockwise className="h-3.5 w-3.5" weight="bold" />
              )}
              {t('undo')}
            </Button>
          )}
          <Button className="rounded-xl" onClick={dismiss}>
            {t('done')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
});
