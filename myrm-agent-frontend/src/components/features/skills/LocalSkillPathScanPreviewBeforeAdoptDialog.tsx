'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import {
  FolderOpen,
  CheckCircle2,
  AlertTriangle,
  ShieldCheck,
  ShieldAlert,
  Loader2,
  Layers,
  Wrench,
} from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { ScrollArea } from '@/components/primitives/scroll-area';
import { Alert, AlertDescription } from '@/components/primitives/alert';
import type { LocalSkillPathPreviewResponse } from '@/store/skill/types';

interface LocalSkillPathScanPreviewBeforeAdoptDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  previewData: LocalSkillPathPreviewResponse | null;
  isAdopting: boolean;
  onConfirmAdopt: () => void;
}

export const LocalSkillPathScanPreviewBeforeAdoptDialog = memo(
  ({
    open,
    onOpenChange,
    previewData,
    isAdopting,
    onConfirmAdopt,
  }: LocalSkillPathScanPreviewBeforeAdoptDialogProps) => {
    const t = useTranslations('settings.skills.local');

    if (!previewData) {
      return null;
    }

    const { resolved_path, total_discovered, skills, warning_message } = previewData;

    return (
      <Dialog open={open} onOpenChange={(val) => !isAdopting && onOpenChange(val)}>
        <DialogContent className="max-w-2xl max-h-[85vh] flex flex-col p-6 gap-4">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-lg font-semibold">
              <FolderOpen className="h-5 w-5 text-primary" />
              {t('previewDialog.title')}
            </DialogTitle>
            <DialogDescription className="text-sm text-muted-foreground">
              {t('previewDialog.description')}
            </DialogDescription>
          </DialogHeader>

          {/* Path & Count header banner */}
          <div className="flex flex-col gap-2 rounded-lg border bg-muted/40 p-3 text-xs">
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium text-muted-foreground">{t('previewDialog.resolvedPath')}:</span>
              <Badge variant="outline" className="font-mono text-xs max-w-[320px] truncate">
                {resolved_path}
              </Badge>
            </div>
            <div className="flex items-center justify-between gap-2 pt-1 border-t border-border/50">
              <span className="text-muted-foreground">
                {t('previewDialog.discoveredCount', { count: total_discovered })}
              </span>
              {total_discovered > 0 ? (
                <Badge variant="default" className="bg-primary/90 text-primary-foreground">
                  <CheckCircle2 className="h-3 w-3 mr-1" />
                  {total_discovered}
                </Badge>
              ) : (
                <Badge variant="secondary" className="text-muted-foreground">
                  0
                </Badge>
              )}
            </div>
          </div>

          {warning_message && (
            <Alert variant="destructive" className="py-2 text-xs">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription>{warning_message}</AlertDescription>
            </Alert>
          )}

          {/* Discovered skills list */}
          <div className="flex-1 min-h-[220px] overflow-hidden">
            {skills.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-48 rounded-md border border-dashed border-border/70 p-6 text-center text-muted-foreground">
                <Layers className="h-8 w-8 mb-2 opacity-50" />
                <p className="font-medium text-sm">{t('previewDialog.noSkillsFound')}</p>
                <p className="text-xs mt-1 max-w-sm">{t('previewDialog.noSkillsFoundDesc')}</p>
              </div>
            ) : (
              <ScrollArea className="h-[280px] pr-3">
                <div className="space-y-3">
                  {skills.map((skill) => (
                    <div
                      key={skill.name + skill.relative_path}
                      className="rounded-lg border bg-card p-3 shadow-xs transition-colors hover:border-border/90"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-medium text-sm text-foreground">{skill.name}</span>
                            <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                              v{skill.version}
                            </Badge>
                            {skill.category && (
                              <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                                {skill.category}
                              </Badge>
                            )}
                            {skill.is_conflicted ? (
                              <Badge variant="destructive" className="text-[10px] px-1.5 py-0 gap-1">
                                <AlertTriangle className="h-2.5 w-2.5" />
                                {t('previewDialog.conflicted')}
                              </Badge>
                            ) : null}
                            {skill.is_safe ? (
                              <Badge
                                variant="outline"
                                className="text-[10px] px-1.5 py-0 border-emerald-500/40 text-emerald-600 dark:text-emerald-400 gap-1"
                              >
                                <ShieldCheck className="h-2.5 w-2.5" />
                                {t('previewDialog.safe')}
                              </Badge>
                            ) : (
                              <Badge
                                variant="outline"
                                className="text-[10px] px-1.5 py-0 border-amber-500/40 text-amber-600 dark:text-amber-400 gap-1"
                              >
                                <ShieldAlert className="h-2.5 w-2.5" />
                                {t('previewDialog.warning')}
                              </Badge>
                            )}
                          </div>
                          {skill.description && (
                            <p className="text-xs text-muted-foreground mt-1 line-clamp-2 leading-relaxed">
                              {skill.description}
                            </p>
                          )}
                        </div>
                        <span className="text-[10px] font-mono text-muted-foreground shrink-0 bg-muted px-1.5 py-0.5 rounded">
                          {skill.relative_path}
                        </span>
                      </div>

                      {skill.conflict_reason && (
                        <div className="mt-2 text-[11px] text-destructive bg-destructive/10 rounded px-2 py-1 flex items-center gap-1.5">
                          <AlertTriangle className="h-3 w-3 shrink-0" />
                          <span>{skill.conflict_reason}</span>
                        </div>
                      )}

                      {skill.required_tools.length > 0 && (
                        <div className="mt-2 flex items-center gap-1.5 flex-wrap">
                          <Wrench className="h-3 w-3 text-muted-foreground shrink-0" />
                          <span className="text-[10px] text-muted-foreground">{t('previewDialog.tools')}:</span>
                          {skill.required_tools.map((tool) => (
                            <Badge key={tool} variant="outline" className="text-[9px] px-1 py-0 font-mono">
                              {tool}
                            </Badge>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </ScrollArea>
            )}
          </div>

          <DialogFooter className="flex items-center justify-end gap-2 pt-2 border-t">
            <Button
              variant="outline"
              size="sm"
              onClick={() => onOpenChange(false)}
              disabled={isAdopting}
            >
              {t('previewDialog.cancel')}
            </Button>
            <Button
              variant="default"
              size="sm"
              onClick={onConfirmAdopt}
              disabled={isAdopting || total_discovered === 0}
            >
              {isAdopting ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
                  {t('previewDialog.adopting')}
                </>
              ) : (
                t('previewDialog.adopt')
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );
  },
);

LocalSkillPathScanPreviewBeforeAdoptDialog.displayName =
  'LocalSkillPathScanPreviewBeforeAdoptDialog';
