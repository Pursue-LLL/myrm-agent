'use client';

/**
 * [INPUT]
 * - ./useInstanceImport: upload / verify / confirm state machine
 * - ./ImportReportView: verified-backup review
 *
 * [OUTPUT]
 * - ImportCard: pick a backup file, verify it, review what changes, confirm, then restart
 *
 * [POS]
 * Import half of the instance backup panel. Nothing is replaced before the user confirms,
 * and the previous data is kept aside so the restore can be undone. The panel owns the
 * restart notice once the swap is queued.
 */

import { memo, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { CheckCircle, CircleNotch, LockKey, UploadSimple } from '@phosphor-icons/react';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Progress } from '@/components/primitives/progress';
import { ArchiveErrorNotice } from './ArchiveErrorNotice';
import { hasExecutableContent, ImportReportView } from './ImportReportView';
import { useInstanceImport } from './useInstanceImport';

interface ImportCardProps {
  onQueued: () => void;
}

export const ImportCard = memo(function ImportCard({ onQueued }: ImportCardProps) {
  const t = useTranslations('instanceArchive.import');
  const { phase, upload, stage, confirm, cancel } = useInstanceImport(onQueued);
  const fileInput = useRef<HTMLInputElement>(null);
  const [passphrase, setPassphrase] = useState('');
  const [acknowledged, setAcknowledged] = useState(false);

  const pick = (file: File | undefined) => {
    if (file) {
      setAcknowledged(false);
      void upload(file);
    }
  };

  const uploadPercent =
    phase.kind === 'uploading'
      ? Math.round((phase.progress.chunksDone / Math.max(1, phase.progress.chunksTotal)) * 100)
      : 0;

  return (
    <div className="flex flex-col gap-4 rounded-2xl border border-border/60 bg-background/60 p-5 backdrop-blur-xl dark:bg-card/40 sm:p-6">
      <div className="flex items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-primary/20 bg-primary/10 text-primary">
          <UploadSimple className="h-5 w-5" weight="duotone" />
        </span>
        <div className="space-y-1">
          <h3 className="text-sm font-bold text-foreground">{t('title')}</h3>
          <p className="text-xs leading-relaxed text-muted-foreground">{t('description')}</p>
        </div>
      </div>

      <input
        ref={fileInput}
        type="file"
        accept=".zip,application/zip"
        className="sr-only"
        data-testid="instance-archive-file"
        onChange={(event) => {
          pick(event.target.files?.[0]);
          event.target.value = '';
        }}
      />

      {phase.kind === 'idle' && (
        <div className="space-y-3">
          {phase.errorCode && <ArchiveErrorNotice code={phase.errorCode} />}
          <Button size="sm" variant="outline" className="gap-1.5 rounded-xl" onClick={() => fileInput.current?.click()}>
            <UploadSimple className="h-3.5 w-3.5" weight="bold" />
            {t('choose')}
          </Button>
        </div>
      )}

      {phase.kind === 'uploading' && (
        <div className="space-y-2">
          <output className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
            <span className="truncate">{t('uploading', { file: phase.fileName })}</span>
            <span className="shrink-0">{uploadPercent}%</span>
          </output>
          <Progress value={uploadPercent} className="h-1.5" />
          <Button size="sm" variant="ghost" className="rounded-xl" onClick={() => void cancel()}>
            {t('cancel')}
          </Button>
        </div>
      )}

      {phase.kind === 'verifying' && (
        <output className="flex items-center gap-2 text-xs text-muted-foreground">
          <CircleNotch className="h-3.5 w-3.5 animate-spin" />
          {t('verifying')}
        </output>
      )}

      {phase.kind === 'passphrase' && (
        <div className="space-y-3">
          <div className="space-y-1">
            <p className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
              <LockKey className="h-3.5 w-3.5" weight="bold" />
              {t('passphraseTitle')}
            </p>
            <p className="text-xs leading-relaxed text-muted-foreground">{t('passphraseDescription')}</p>
          </div>
          <Input
            type="password"
            autoComplete="off"
            value={passphrase}
            onChange={(event) => setPassphrase(event.target.value)}
            placeholder={t('passphrase')}
            aria-label={t('passphrase')}
            className="h-9 text-xs"
          />
          {phase.errorCode && <ArchiveErrorNotice code={phase.errorCode} />}
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              className="rounded-xl"
              disabled={!passphrase}
              onClick={() => {
                const secret = passphrase;
                setPassphrase('');
                void stage(phase.sessionId, { passphrase: secret });
              }}
            >
              {t('unlock')}
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="rounded-xl"
              onClick={() => {
                setPassphrase('');
                void stage(phase.sessionId, { skipSecrets: true });
              }}
            >
              {t('skipKeys')}
            </Button>
            <Button size="sm" variant="ghost" className="rounded-xl" onClick={() => void cancel(phase.sessionId)}>
              {t('cancel')}
            </Button>
          </div>
        </div>
      )}

      {(phase.kind === 'review' || phase.kind === 'confirming') && (
        <div className="space-y-4">
          <ImportReportView report={phase.report} acknowledged={acknowledged} onAcknowledgedChange={setAcknowledged} />
          {phase.kind === 'review' && phase.errorCode && <ArchiveErrorNotice code={phase.errorCode} />}
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              className="gap-1.5 rounded-xl"
              disabled={phase.kind === 'confirming' || (hasExecutableContent(phase.report) && !acknowledged)}
              onClick={() => void confirm(phase.sessionId, phase.report, acknowledged)}
            >
              {phase.kind === 'confirming' && <CircleNotch className="h-3.5 w-3.5 animate-spin" />}
              {t('confirm')}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="rounded-xl"
              disabled={phase.kind === 'confirming'}
              onClick={() => void cancel(phase.sessionId)}
            >
              {t('cancel')}
            </Button>
          </div>
        </div>
      )}

      {phase.kind === 'queued' && (
        <output className="flex items-center gap-2 text-sm font-semibold text-emerald-600 dark:text-emerald-400">
          <CheckCircle className="h-4 w-4" weight="fill" />
          {t('queued')}
        </output>
      )}
    </div>
  );
});
