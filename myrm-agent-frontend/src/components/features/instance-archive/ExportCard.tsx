'use client';

/**
 * [INPUT]
 * - ./useInstanceExport: export job state machine
 * - @/lib/instance-archive/reentry: reentryGroups
 *
 * [OUTPUT]
 * - ExportCard: create a whole-workspace backup, optionally sealing API keys with a passphrase, say what could
 *   not be included (credentials to re-enter, items that could not be read), and save it
 *
 * [POS]
 * Export half of the instance backup panel.
 */

import { memo, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Archive, CheckCircle, CircleNotch, DownloadSimple, LockKey, WarningCircle } from '@phosphor-icons/react';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Progress } from '@/components/primitives/progress';
import { Switch } from '@/components/primitives/switch';
import { formatBytes } from '@/lib/instance-archive/format';
import { reentryGroups } from '@/lib/instance-archive/reentry';
import { cn } from '@/lib/utils/classnameUtils';
import { ArchiveErrorNotice } from './ArchiveErrorNotice';
import { useInstanceExport } from './useInstanceExport';

interface ExportCardProps {
  canProtectSecrets: boolean;
}

const MIN_PASSPHRASE = 8;

export const ExportCard = memo(function ExportCard({ canProtectSecrets }: ExportCardProps) {
  const t = useTranslations('instanceArchive.export');
  const tGroup = useTranslations('instanceArchive.groups');
  const { phase, start, save, discard } = useInstanceExport();
  const [includeKeys, setIncludeKeys] = useState(false);
  const [passphrase, setPassphrase] = useState('');
  const [repeat, setRepeat] = useState('');

  const passphraseError = useMemo(() => {
    if (!includeKeys) {
      return null;
    }
    if (passphrase.length < MIN_PASSPHRASE) {
      return 'short';
    }
    return passphrase === repeat ? null : 'mismatch';
  }, [includeKeys, passphrase, repeat]);

  const running = phase.kind === 'running';
  const job = phase.kind === 'idle' ? null : phase.job;
  const percent = job && job.bytes_total > 0 ? Math.min(100, Math.round((job.bytes_done / job.bytes_total) * 100)) : 0;
  const notIncluded = job ? reentryGroups(job.reentry) : [];
  const unreadableCount = job?.unreadable_count ?? 0;
  const incomplete = unreadableCount > 0;

  return (
    <div className="flex flex-col gap-4 rounded-2xl border border-border/60 bg-background/60 p-5 backdrop-blur-xl dark:bg-card/40 sm:p-6">
      <div className="flex items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-primary/20 bg-primary/10 text-primary">
          <Archive className="h-5 w-5" weight="duotone" />
        </span>
        <div className="space-y-1">
          <h3 className="text-sm font-bold text-foreground">{t('title')}</h3>
          <p className="text-xs leading-relaxed text-muted-foreground">{t('description')}</p>
        </div>
      </div>

      {phase.kind === 'idle' && (
        <div className="space-y-4">
          {canProtectSecrets ? (
            <div className="space-y-3 rounded-xl border border-border/50 bg-muted/20 p-3">
              <label className="flex cursor-pointer items-start justify-between gap-3">
                <span className="space-y-0.5">
                  <span className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                    <LockKey className="h-3.5 w-3.5" weight="bold" />
                    {t('includeKeys')}
                  </span>
                  <span className="block text-xs leading-relaxed text-muted-foreground">{t('includeKeysHint')}</span>
                </span>
                <Switch checked={includeKeys} onCheckedChange={setIncludeKeys} aria-label={t('includeKeys')} />
              </label>
              {includeKeys && (
                <div className="grid gap-2 sm:grid-cols-2">
                  <Input
                    type="password"
                    autoComplete="new-password"
                    value={passphrase}
                    onChange={(event) => setPassphrase(event.target.value)}
                    placeholder={t('passphrase')}
                    aria-label={t('passphrase')}
                    className="h-9 text-xs"
                  />
                  <Input
                    type="password"
                    autoComplete="new-password"
                    value={repeat}
                    onChange={(event) => setRepeat(event.target.value)}
                    placeholder={t('passphraseRepeat')}
                    aria-label={t('passphraseRepeat')}
                    className="h-9 text-xs"
                  />
                  <p className="text-xs text-muted-foreground sm:col-span-2">
                    {passphraseError === 'mismatch' && repeat ? t('passphraseMismatch') : t('passphraseHint')}
                  </p>
                </div>
              )}
            </div>
          ) : (
            <p className="rounded-xl border border-border/50 bg-muted/20 p-3 text-xs leading-relaxed text-muted-foreground">
              {t('keysNotIncluded')}
            </p>
          )}
          {phase.errorCode && <ArchiveErrorNotice code={phase.errorCode} />}
          <Button
            size="sm"
            className="gap-1.5 rounded-xl"
            disabled={passphraseError !== null}
            onClick={() => {
              const secret = includeKeys ? passphrase : undefined;
              setPassphrase('');
              setRepeat('');
              void start(secret);
            }}
          >
            <Archive className="h-3.5 w-3.5" weight="bold" />
            {t('start')}
          </Button>
        </div>
      )}

      {running && (
        <div className="space-y-2">
          <output className="flex items-center justify-between text-xs text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <CircleNotch className="h-3.5 w-3.5 animate-spin" />
              {t('running')}
            </span>
            <span>{t('progress', { done: phase.job.files_done, total: phase.job.files_total })}</span>
          </output>
          <Progress value={percent} className="h-1.5" />
        </div>
      )}

      {(phase.kind === 'ready' || phase.kind === 'downloading' || phase.kind === 'saved') && job && (
        <div className="space-y-3">
          <div
            className={cn(
              'flex items-center gap-2 text-sm font-semibold',
              incomplete ? 'text-amber-700 dark:text-amber-300' : 'text-emerald-600 dark:text-emerald-400',
            )}
          >
            {incomplete ? (
              <WarningCircle className="h-4 w-4 shrink-0" weight="fill" />
            ) : (
              <CheckCircle className="h-4 w-4 shrink-0" weight="fill" />
            )}
            {phase.kind === 'saved' ? t('saved') : t('ready', { size: formatBytes(job.size_bytes ?? 0) })}
          </div>
          {job.config_key_carried && <p className="text-xs leading-relaxed text-muted-foreground">{t('keysSealed')}</p>}
          {incomplete && (
            <output className="block rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs leading-relaxed text-amber-700 dark:text-amber-300">
              {t('unreadable', { count: unreadableCount })}
            </output>
          )}
          {notIncluded.length > 0 && (
            <div className="space-y-1 text-xs text-muted-foreground">
              <p>{t('notIncluded')}</p>
              <ul className="list-inside list-disc space-y-0.5">
                {notIncluded.map((group) => (
                  <li key={group}>{tGroup(group)}</li>
                ))}
              </ul>
            </div>
          )}
          {phase.kind === 'ready' && phase.errorCode && <ArchiveErrorNotice code={phase.errorCode} />}
          {phase.kind === 'saved' && <p className="text-xs leading-relaxed text-muted-foreground">{t('keepSafe')}</p>}
          <div className="flex flex-wrap gap-2">
            {phase.kind !== 'saved' && (
              <Button
                size="sm"
                className="gap-1.5 rounded-xl"
                disabled={phase.kind === 'downloading'}
                onClick={() => void save(job)}
              >
                {phase.kind === 'downloading' ? (
                  <CircleNotch className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <DownloadSimple className="h-3.5 w-3.5" weight="bold" />
                )}
                {phase.kind === 'downloading' ? t('saving', { size: formatBytes(phase.received) }) : t('save')}
              </Button>
            )}
            <Button
              size="sm"
              variant="outline"
              className="rounded-xl"
              disabled={phase.kind === 'downloading'}
              onClick={() => void discard(job)}
            >
              {phase.kind === 'saved' ? t('done') : t('discard')}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
});
