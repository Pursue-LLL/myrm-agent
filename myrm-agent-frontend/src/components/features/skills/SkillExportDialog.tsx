'use client';

import { memo, useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { Download, AlertTriangle, CheckCircle2, Loader2, FileCode2 } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import { ScrollArea } from '@/components/primitives/scroll-area';
import { Alert, AlertDescription, AlertTitle } from '@/components/primitives/alert';
import { previewSkillPackage, downloadSkill, triggerDownload } from '@/services/skill';
import type { PackagePreviewResponse } from '@/services/skill';
import type { Skill } from '@/store/skill/types';
import { toast } from '@/hooks/useToast';

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

  useEffect(() => {
    if (open && skill) {
      setIsLoading(true);
      setPreview(null);
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
    }
  }, [open, skill, onOpenChange, t]);

  const handleExport = useCallback(
    async (applyRedactions: boolean) => {
      if (!skill) return;
      setIsExporting(true);
      try {
        const blob = await downloadSkill(skill.id, applyRedactions);
        triggerDownload(blob, `${skill.name}_v${skill.version || '1.0.0'}.zip`);
        toast({
          title: t('exportSuccess'),
        });
        onOpenChange(false);
      } catch (err) {
        toast({
          title: t('exportFailed'),
          description: err instanceof Error ? err.message : String(err),
          variant: 'destructive',
        });
      } finally {
        setIsExporting(false);
      }
    },
    [skill, onOpenChange, t],
  );

  if (!skill) return null;

  const hasRedactions = preview?.redactions && Object.keys(preview.redactions).length > 0;

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
                  </AlertDescription>
                </Alert>
              ) : (
                <Alert variant="destructive" className="bg-destructive/5">
                  <AlertTriangle className="h-4 w-4" />
                  <AlertTitle>{t('warningTitle')}</AlertTitle>
                  <AlertDescription>{t('warningDescription')}</AlertDescription>
                </Alert>
              )}

              {hasRedactions && (
                <div className="flex-1 flex flex-col min-h-0 border rounded-md">
                  <div className="bg-muted px-3 py-2 text-sm font-medium border-b flex items-center gap-2">
                    <FileCode2 className="h-4 w-4" />
                    {t('diffPreview')}
                  </div>
                  <ScrollArea className="flex-1 p-0">
                    {Object.entries(preview.redactions!).map(([filename, redactions]) => (
                      <div key={filename} className="mb-4 last:mb-0">
                        <div className="bg-muted/50 px-3 py-1.5 text-xs font-mono border-y first:border-t-0">
                          {filename}
                        </div>
                        <div className="p-3 space-y-3">
                          {redactions.map((r, i) => (
                            <div key={i} className="text-xs font-mono border rounded overflow-hidden">
                              <div className="bg-muted/30 px-2 py-1 border-b text-[10px] text-muted-foreground flex justify-between">
                                <span>Line {r.line_number}</span>
                                <span className="text-amber-600 dark:text-amber-400">{r.reason}</span>
                              </div>
                              <div className="grid grid-cols-1 divide-y">
                                <div className="bg-red-500/10 text-red-700 dark:text-red-400 p-2 overflow-x-auto whitespace-pre">
                                  <span className="select-none opacity-50 mr-2">-</span>
                                  {r.original}
                                </div>
                                <div className="bg-green-500/10 text-green-700 dark:text-green-400 p-2 overflow-x-auto whitespace-pre">
                                  <span className="select-none opacity-50 mr-2">+</span>
                                  {r.redacted}
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </ScrollArea>
                </div>
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
                {isExporting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Download className="mr-2 h-4 w-4" />}
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
