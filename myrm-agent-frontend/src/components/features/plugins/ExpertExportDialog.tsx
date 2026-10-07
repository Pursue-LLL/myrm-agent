'use client';

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';

import { IconAlertTriangle, IconCheckCircle, IconDownload, IconLoader } from '@/components/features/icons/PremiumIcons';
import RedactionReview from '@/components/features/redaction/RedactionReview';
import { keepEveryFinding, useRedactionDecisions } from '@/components/features/redaction/useRedactionDecisions';
import { Alert, AlertDescription, AlertTitle } from '@/components/primitives/alert';
import { Button } from '@/components/primitives/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import { toast } from '@/hooks/shared/useToast';
import { cn } from '@/lib/utils/classnameUtils';
import { triggerDownload } from '@/lib/utils/fileUtils';
import {
  downloadExpertPackage,
  EXPERT_EXPORT_CHANGED_SINCE_PREVIEW,
  ExpertExportError,
  expertExportErrorCode,
  previewExpertExport,
  type ExpertExportErrorCode,
  type ExpertExportPreview,
} from '@/services/expertPackage';
import { formatFileSize } from '@/types/artifact';

import { MOBILE_FULLSCREEN_DIALOG } from './dialogLayout';
import ExpertExportClosure from './ExpertExportClosure';

interface ExpertExportDialogProps {
  agentId: string;
  agentName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** What a failed request is reported as: a stable code the dialog has words for, or the generic sentence. */
type FailureKey = ExpertExportErrorCode | 'generic';

/** The backend's English detail is a diagnostic: it goes to the console and only the key reaches the UI. */
function diagnoseFailure(error: unknown): FailureKey {
  console.error('Expert export request failed:', error);
  return expertExportErrorCode(error) ?? 'generic';
}

/**
 * Preview, review and download one expert as an Agent Plugins package.
 * Upper half: what ships and what stays behind; lower half: the shared redaction review.
 */
const ExpertExportDialog = memo(({ agentId, agentName, open, onOpenChange }: ExpertExportDialogProps) => {
  const t = useTranslations('agent.expertExport');
  const [preview, setPreview] = useState<ExpertExportPreview | null>(null);
  const [loadFailure, setLoadFailure] = useState<FailureKey | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const { ignored, reset, toggle, toggleAll } = useRedactionDecisions();

  // A code without wording of its own (e.g. one only meaningful on export) reads as the generic sentence.
  const failureText = useCallback(
    (failure: FailureKey): string => {
      const key = `errors.${failure}` as Parameters<typeof t.has>[0];
      return t.has(key) ? t(key) : t('errors.generic');
    },
    [t],
  );

  const loadPreview = useCallback(async () => {
    setIsLoading(true);
    setPreview(null);
    setLoadFailure(null);
    reset();
    try {
      const loaded = await previewExpertExport(agentId);
      if (loaded.build_error) {
        console.warn('Expert package cannot be built:', loaded.build_error);
      }
      setPreview(loaded);
    } catch (error) {
      setLoadFailure(diagnoseFailure(error));
    } finally {
      setIsLoading(false);
    }
  }, [agentId, reset]);

  useEffect(() => {
    if (open) {
      void loadPreview();
    }
  }, [open, loadPreview]);

  const findings = preview?.redactions ?? null;
  const hasFindings = findings !== null && Object.keys(findings).length > 0;

  const handleExport = useCallback(
    async (keepOriginal: boolean) => {
      if (!preview) {
        return;
      }
      setIsExporting(true);
      try {
        const { blob, filename } = await downloadExpertPackage({
          agentId,
          // Keeping everything is an explicit decision on every finding; the server refuses unreviewed ones.
          applyRedactions: !keepOriginal,
          ignoredRedactions: keepOriginal ? keepEveryFinding(findings ?? {}) : ignored,
          reviewDigest: preview.review_digest,
        });
        await triggerDownload(blob, filename || `${preview.plugin_name}_v${preview.version}.zip`);
        toast({ title: t('exportSuccess') });
        onOpenChange(false);
      } catch (error) {
        // The expert changed after it was reviewed: kept-finding indices no longer point at the same text.
        if (error instanceof ExpertExportError && error.code === EXPERT_EXPORT_CHANGED_SINCE_PREVIEW) {
          toast({ title: t('changedSinceReview'), variant: 'destructive' });
          void loadPreview();
          return;
        }
        toast({ title: t('exportFailed'), description: failureText(diagnoseFailure(error)), variant: 'destructive' });
      } finally {
        setIsExporting(false);
      }
    },
    [agentId, failureText, findings, ignored, loadPreview, onOpenChange, preview, t],
  );

  // A package that cannot be built would fail the same way on export, so it is not offered.
  const buildable = preview !== null && preview.build_error === null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={cn('flex max-h-[85vh] flex-col sm:max-w-[680px]', MOBILE_FULLSCREEN_DIALOG)}>
        <DialogHeader>
          <DialogTitle>{t('title', { name: agentName })}</DialogTitle>
          <DialogDescription>{t('description')}</DialogDescription>
        </DialogHeader>

        <div className="flex min-h-0 flex-1 flex-col gap-4 py-2">
          {isLoading && (
            <div className="flex flex-col items-center justify-center gap-3 py-10 text-muted-foreground">
              <IconLoader className="h-8 w-8 animate-spin text-primary" />
              <p className="text-sm">{t('scanning')}</p>
            </div>
          )}

          {loadFailure && (
            <Alert variant="destructive">
              <IconAlertTriangle className="h-4 w-4" />
              <AlertTitle>{t('previewFailed')}</AlertTitle>
              <AlertDescription>{failureText(loadFailure)}</AlertDescription>
            </Alert>
          )}

          {preview && (
            <>
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                <span className="font-mono">
                  {preview.plugin_name} · v{preview.version}
                </span>
                {preview.package_bytes !== null && <span>{formatFileSize(preview.package_bytes)}</span>}
              </div>

              {preview.build_error && (
                <Alert variant="destructive">
                  <IconAlertTriangle className="h-4 w-4" />
                  <AlertTitle>{t('buildErrorTitle')}</AlertTitle>
                  <AlertDescription className="break-words">{t('errors.package_rejected')}</AlertDescription>
                </Alert>
              )}

              <div className={cn('overflow-y-auto pr-1', hasFindings ? 'max-h-[38vh] shrink-0' : 'min-h-0 flex-1')}>
                <ExpertExportClosure preview={preview} />
              </div>

              {hasFindings ? (
                <>
                  <Alert variant="destructive" className="bg-destructive/5">
                    <IconAlertTriangle className="h-4 w-4" />
                    <AlertTitle>{t('warningTitle')}</AlertTitle>
                    <AlertDescription>{t('warningDescription')}</AlertDescription>
                  </Alert>
                  <RedactionReview
                    findings={findings}
                    ignored={ignored}
                    onToggle={toggle}
                    onToggleAll={toggleAll}
                    disabled={isExporting}
                  />
                </>
              ) : (
                <Alert className="border-emerald-200 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/30">
                  <IconCheckCircle className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
                  <AlertTitle className="text-emerald-800 dark:text-emerald-300">{t('safeTitle')}</AlertTitle>
                  <AlertDescription className="text-emerald-700 dark:text-emerald-400">
                    {t('safeDescription')}
                  </AlertDescription>
                </Alert>
              )}
            </>
          )}
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isExporting}>
            {t('actions.cancel')}
          </Button>
          {buildable && hasFindings && (
            <Button
              variant="destructive"
              onClick={() => void handleExport(true)}
              disabled={isExporting}
              className="sm:mr-auto"
            >
              {t('actions.exportOriginal')}
            </Button>
          )}
          {preview && (
            <Button onClick={() => void handleExport(false)} disabled={!buildable || isExporting}>
              {isExporting ? (
                <IconLoader className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <IconDownload className="mr-2 h-4 w-4" />
              )}
              {hasFindings ? t('actions.exportRedacted') : t('actions.export')}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
});

ExpertExportDialog.displayName = 'ExpertExportDialog';

export default ExpertExportDialog;
