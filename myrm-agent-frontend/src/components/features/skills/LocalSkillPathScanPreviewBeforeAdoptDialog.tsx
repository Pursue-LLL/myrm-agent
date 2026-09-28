'use client';

import { memo, useState, useEffect, useMemo, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import {
  FolderOpen,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  Layers,
  CheckSquare,
  Square,
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
import { LocalSkillPreviewCard } from './LocalSkillPreviewCard';

interface LocalSkillPathScanPreviewBeforeAdoptDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  previewData: LocalSkillPathPreviewResponse | null;
  isAdopting: boolean;
  onConfirmAdopt: (selectedSkillIds: string[], allowUntrusted?: boolean) => void;
  onAddPathOnly?: () => void;
}

export const LocalSkillPathScanPreviewBeforeAdoptDialog = memo(
  ({
    open,
    onOpenChange,
    previewData,
    isAdopting,
    onConfirmAdopt,
    onAddPathOnly,
  }: LocalSkillPathScanPreviewBeforeAdoptDialogProps) => {
    const t = useTranslations('settings.skills.local');
    const [selectedIds, setSelectedIds] = useState<string[]>([]);
    const [allowUntrusted, setAllowUntrusted] = useState(false);

    const skills = useMemo(() => previewData?.skills || [], [previewData]);

    const hasBlockedSkills = useMemo(() => {
      return skills.some((s) => {
        const score = s.security_score ?? (s.security?.score ?? (s.is_safe ? 100 : 40));
        return score < 50;
      });
    }, [skills]);

    // 可采纳的安全候选技能列表（默认过滤掉安全门禁拦截项，若勾选受控免责则全量可选）
    const adoptableSkills = useMemo(() => {
      return skills.filter((s) => {
        if (!s.skill_id) {
          return false;
        }
        const score = s.security_score ?? (s.security?.score ?? (s.is_safe ? 100 : 40));
        return allowUntrusted || score >= 50;
      });
    }, [skills, allowUntrusted]);

    // 初始化默认勾选所有非冲突且通过安全门禁的有效技能
    useEffect(() => {
      if (open && previewData?.skills) {
        setAllowUntrusted(false);
        const defaultSelected = previewData.skills
          .filter((s) => {
            const score = s.security_score ?? (s.security?.score ?? (s.is_safe ? 100 : 40));
            return !s.is_conflicted && s.skill_id && score >= 50;
          })
          .map((s) => s.skill_id);
        setSelectedIds(defaultSelected);
      }
    }, [open, previewData]);

    const handleToggleSkill = useCallback((skillId: string) => {
      setSelectedIds((prev) => (prev.includes(skillId) ? prev.filter((id) => id !== skillId) : [...prev, skillId]));
    }, []);

    const handleSelectAll = useCallback(() => {
      const allSafeIds = adoptableSkills.map((s) => s.skill_id);
      setSelectedIds(allSafeIds);
    }, [adoptableSkills]);

    const handleDeselectAll = useCallback(() => {
      setSelectedIds([]);
    }, []);

    if (!previewData) {
      return null;
    }

    const { resolved_path, total_discovered, warning_message } = previewData;
    const isAllSelected = adoptableSkills.length > 0 && selectedIds.length === adoptableSkills.length;

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
              <div className="flex items-center gap-2">
                {total_discovered > 0 && (
                  <span className="text-muted-foreground">
                    {t('previewDialog.selectedCount', { count: selectedIds.length })}
                  </span>
                )}
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
          </div>

          {warning_message && (
            <Alert variant="destructive" className="py-2 text-xs">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription>{warning_message}</AlertDescription>
            </Alert>
          )}

          {/* Multi-select controls */}
          {skills.length > 0 && (
            <div className="flex items-center justify-between text-xs px-1 text-muted-foreground">
              <span>{t('previewDialog.selectedCount', { count: selectedIds.length })}</span>
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 px-2 text-xs"
                  data-testid="preview-toggle-selection-btn"
                  onClick={isAllSelected ? handleDeselectAll : handleSelectAll}
                >
                  {isAllSelected ? (
                    <>
                      <Square className="h-3 w-3 mr-1" />
                      {t('previewDialog.deselectAll')}
                    </>
                  ) : (
                    <>
                      <CheckSquare className="h-3 w-3 mr-1" />
                      {t('previewDialog.selectAll')}
                    </>
                  )}
                </Button>
              </div>
            </div>
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
                    <LocalSkillPreviewCard
                      key={skill.name + skill.relative_path}
                      skill={skill}
                      isSelected={selectedIds.includes(skill.skill_id)}
                      onToggle={handleToggleSkill}
                      allowUntrusted={allowUntrusted}
                    />
                  ))}
                </div>
              </ScrollArea>
            )}
          </div>

          {/* Controlled Override Banner for High-Risk Skills */}
          {hasBlockedSkills && (
            <div
              data-testid="allow-untrusted-warning-banner"
              className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 dark:bg-amber-500/15 p-2.5 text-xs text-amber-900 dark:text-amber-200"
            >
              <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
              <label className="flex items-center gap-2 cursor-pointer flex-1 select-none font-medium">
                <input
                  type="checkbox"
                  data-testid="allow-untrusted-skills-checkbox"
                  checked={allowUntrusted}
                  onChange={(e) => setAllowUntrusted(e.target.checked)}
                  className="h-3.5 w-3.5 rounded border-amber-400 text-amber-600 focus:ring-amber-500 cursor-pointer"
                />
                <span>{t('previewDialog.allowUntrustedDescription')}</span>
              </label>
            </div>
          )}

          <DialogFooter className="flex items-center justify-between gap-2 pt-2 border-t">
            {onAddPathOnly ? (
              <Button
                data-testid="preview-adopt-add-path-only-btn"
                variant="ghost"
                size="sm"
                onClick={onAddPathOnly}
                disabled={isAdopting}
                className="text-xs text-muted-foreground hover:text-foreground"
              >
                {t('previewDialog.addPathOnly')}
              </Button>
            ) : (
              <div />
            )}
            <div className="flex items-center gap-2">
              <Button
                data-testid="preview-adopt-cancel-btn"
                variant="outline"
                size="sm"
                onClick={() => onOpenChange(false)}
                disabled={isAdopting}
              >
                {t('previewDialog.cancel')}
              </Button>
              <Button
                data-testid="preview-adopt-confirm-btn"
                variant="default"
                size="sm"
                onClick={() => {
                  if (allowUntrusted) {
                    onConfirmAdopt(selectedIds, true);
                  } else {
                    onConfirmAdopt(selectedIds);
                  }
                }}
                disabled={isAdopting || total_discovered === 0 || selectedIds.length === 0}
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
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );
  },
);

LocalSkillPathScanPreviewBeforeAdoptDialog.displayName = 'LocalSkillPathScanPreviewBeforeAdoptDialog';
