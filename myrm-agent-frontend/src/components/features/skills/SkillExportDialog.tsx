'use client';

import { memo, useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { Download, AlertTriangle, CheckCircle2, Loader2 } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import { Alert, AlertDescription, AlertTitle } from '@/components/primitives/alert';
import { previewSkillPackage, downloadSkill, SKILL_CHANGED_SINCE_PREVIEW } from '@/services/skill';
import { triggerDownload } from '@/lib/utils/fileUtils';
import type { PackagePreviewResponse } from '@/services/skill';
import type { Skill } from '@/store/skill/types';
import { toast } from '@/hooks/shared/useToast';
import RedactionReview from '@/components/features/redaction/RedactionReview';
import { useRedactionDecisions } from '@/components/features/redaction/useRedactionDecisions';

interface SkillExportDialogProps {
  skill: Skill | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const SkillExportDialog = memo(({ skill, open, onOpenChange }: SkillExportDialogProps) => {
  const t = useTranslations('settings.skills.export');
  const [isLoading, setIsLoading] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [preview, setPreview] = useState<PackagePreviewResponse | null>(null);
  const { ignored, reset, toggle, toggleAll } = useRedactionDecisions();

  const loadPreview = useCallback(() => {
    if (!skill) {
      return;
    }
    setIsLoading(true);
    setPreview(null);
    reset();
    previewSkillPackage(skill.id)
      .then((res) => {
        setPreview(res);
      })
      .catch((err) => {
        toast({
          title: t('previewFailed'),
          description: err.message,
          variant: 'destructive',
        });
        onOpenChange(false);
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, [skill, onOpenChange, t, reset]);

  useEffect(() => {
    if (open) {
      loadPreview();
    }
  }, [open, loadPreview]);

  const handleExport = useCallback(
    async (applyRedactions: boolean) => {
      if (!skill) {
        return;
      }
      setIsExporting(true);
      try {
        const { blob, filename } = await downloadSkill(
          skill.id,
          applyRedactions,
          ignored,
          'agent_plugin',
          preview?.review_digest,
        );
        await triggerDownload(blob, filename || `${skill.name}_v${skill.version || '1.0.0'}.zip`);
        toast({
          title: t('exportSuccess'),
        });
        onOpenChange(false);
      } catch (err) {
        // 技能在预览后被修改：忽略索引已失效，必须重新审阅，不能带着旧决定导出
        if ((err as { code?: string }).code === SKILL_CHANGED_SINCE_PREVIEW) {
          toast({ title: t('changedSinceReview'), variant: 'destructive' });
          loadPreview();
          return;
        }
        toast({
          title: t('exportFailed'),
          description: err instanceof Error ? err.message : String(err),
          variant: 'destructive',
        });
      } finally {
        setIsExporting(false);
      }
    },
    [skill, onOpenChange, t, ignored, preview, loadPreview],
  );

  if (!skill) {
    return null;
  }

  const findings = preview?.redactions ?? null;
  const hasRedactions = findings !== null && Object.keys(findings).length > 0;
  const evalCasesNote =
    preview && preview.eval_cases_count > 0 ? ` ${t('evalCasesIncluded', { count: preview.eval_cases_count })}` : '';

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px] max-h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>{t('title', { name: skill.name })}</DialogTitle>
          <DialogDescription>{t('description')}</DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-hidden flex flex-col gap-4 py-4">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
              <Loader2 className="h-8 w-8 animate-spin mb-4" />
              <p>{t('scanning')}</p>
            </div>
          ) : preview ? (
            <>
              {preview.is_safe ? (
                <Alert className="bg-green-50 dark:bg-green-950/30 border-green-200 dark:border-green-800">
                  <CheckCircle2 className="h-4 w-4 text-green-600 dark:text-green-400" />
                  <AlertTitle className="text-green-800 dark:text-green-300">{t('safeTitle')}</AlertTitle>
                  <AlertDescription className="text-green-700 dark:text-green-400">
                    {t('safeDescription')}
                    {evalCasesNote}
                  </AlertDescription>
                </Alert>
              ) : (
                <Alert variant="destructive" className="bg-destructive/5">
                  <AlertTriangle className="h-4 w-4" />
                  <AlertTitle>{t('warningTitle')}</AlertTitle>
                  <AlertDescription>
                    {t('warningDescription')}
                    {evalCasesNote}
                  </AlertDescription>
                </Alert>
              )}

              {hasRedactions && (
                <RedactionReview findings={findings} ignored={ignored} onToggle={toggle} onToggleAll={toggleAll} />
              )}
            </>
          ) : null}
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isExporting}>
            {t('cancel')}
          </Button>
          {!isLoading && preview && (
            <>
              {hasRedactions && (
                <Button
                  variant="destructive"
                  onClick={() => handleExport(false)}
                  disabled={isExporting}
                  className="sm:mr-auto"
                >
                  {t('exportOriginal')}
                </Button>
              )}
              <Button onClick={() => handleExport(true)} disabled={isExporting}>
                {isExporting ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Download className="mr-2 h-4 w-4" />
                )}
                {hasRedactions ? t('exportRedacted') : t('export')}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
});

SkillExportDialog.displayName = 'SkillExportDialog';

export default SkillExportDialog;
