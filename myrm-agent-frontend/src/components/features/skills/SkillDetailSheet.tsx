'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { Package, Trash2, Loader2, Download, Zap } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/primitives/sheet';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
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
import { Input } from '@/components/primitives/input';
import type { Skill } from '@/store/skill/types';
import { getCategoryIcon, getCategoryColor } from './skillCategories';
import { SecurityScanSection } from './SkillDetailHelpers';
import SkillExportDialog from './SkillExportDialog';
import { useSkillDetailSheet } from './useSkillDetailSheet';
import { SkillDetailSheetContent } from './SkillDetailSheetContent';

interface SkillDetailSheetProps {
  skill: Skill | null;
  open: boolean;
  isEnabled: boolean;
  showDeleteButton?: boolean;
  onOpenChange: (open: boolean) => void;
  onToggle?: (skillId: string) => Promise<void>;
  onDelete?: (skill: Skill) => Promise<void>;
  onTrustChange?: () => void;
  onLifecycleAction?: (skill: Skill, action: import('@/store/skill/types').SkillLifecycleAction) => void;
}

const SkillDetailSheet = memo(
  ({
    skill,
    open,
    isEnabled,
    showDeleteButton = false,
    onOpenChange,
    onToggle,
    onDelete,
    onTrustChange,
    onLifecycleAction,
  }: SkillDetailSheetProps) => {
    const t = useTranslations('settings.skills');

    const sheet = useSkillDetailSheet({
      skill,
      open,
      isEnabled,
      onOpenChange,
      onToggle,
      onDelete,
      onTrustChange,
      t,
    });

    if (!skill) return null;

    const category = skill.category || 'other';
    const CategoryIcon = getCategoryIcon(category);
    const categoryColor = getCategoryColor(category);

    return (
      <>
        <Sheet open={open} onOpenChange={onOpenChange}>
          <SheetContent side="right" className="w-full sm:max-w-lg flex flex-col p-0 overflow-hidden">
            <SheetHeader className="p-6 pb-4 border-b shrink-0">
              <div className="flex items-start gap-4">
                <div
                  className={cn('flex-shrink-0 w-12 h-12 rounded-xl flex items-center justify-center', categoryColor)}
                >
                  <CategoryIcon size={24} />
                </div>
                <div className="flex-1 min-w-0">
                  <SheetTitle className="text-xl font-semibold truncate">{skill.name}</SheetTitle>
                  <SheetDescription className="mt-1">
                    <span className="flex items-center gap-3 text-sm">
                      <span className="flex items-center gap-1">
                        <Package size={14} />v{skill.version}
                      </span>
                      <Badge variant="secondary" className={cn('text-xs', categoryColor)}>
                        {t(`categories.${category}` as Parameters<typeof t>[0])}
                      </Badge>
                      {skill.always && (
                        <Badge
                          variant="outline"
                          className="text-xs border-emerald-300 text-emerald-600 dark:border-emerald-700 dark:text-emerald-400"
                        >
                          {t('card.alwaysEnabled')}
                        </Badge>
                      )}
                    </span>
                  </SheetDescription>
                </div>
              </div>
            </SheetHeader>

            <div className="flex-1 overflow-y-auto px-6">
              <SkillDetailSheetContent
                skill={skill}
                skillContent={sheet.skillContent}
                isLoadingContent={sheet.isLoadingContent}
                isUserTrustable={sheet.isUserTrustable}
                isUserTrusted={sheet.isUserTrusted}
                isTrusting={sheet.isTrusting}
                isEvolutionLocked={sheet.isEvolutionLocked}
                isTogglingLock={sheet.isTogglingLock}
                isPathInvalid={sheet.isPathInvalid}
                isRevealing={sheet.isRevealing}
                hasRequirements={sheet.hasRequirements}
                hasEnvRequirements={sheet.hasEnvRequirements}
                envVars={sheet.envVars}
                envVarsDirty={sheet.envVarsDirty}
                isSavingEnv={sheet.isSavingEnv}
                reloadSkillContent={sheet.reloadSkillContent}
                handleUntrust={sheet.handleUntrust}
                handleToggleEvolutionLock={sheet.handleToggleEvolutionLock}
                handleReveal={sheet.handleReveal}
                handleEnvVarChange={sheet.handleEnvVarChange}
                handleSaveEnvVars={sheet.handleSaveEnvVars}
                setShowTrustConfirm={sheet.setShowTrustConfirm}
                setShowDeleteConfirm={sheet.setShowDeleteConfirm}
                onLifecycleAction={onLifecycleAction}
                t={t}
              />
            </div>

            {/* Footer actions */}
            <div className="p-4 border-t flex items-center justify-between shrink-0">
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => sheet.setShowExportDialog(true)}
                  className="hidden sm:flex"
                >
                  <Download className="h-4 w-4 mr-2" />
                  {t('export')}
                </Button>
                {showDeleteButton && (
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => sheet.setShowDeleteConfirm(true)}
                    disabled={sheet.isDeleting}
                  >
                    {sheet.isDeleting ? (
                      <Loader2 className="animate-spin mr-2" size={16} />
                    ) : (
                      <Trash2 size={16} className="mr-2" />
                    )}
                    {t('detail.delete')}
                  </Button>
                )}
                {skill.type === 'local' && (
                  <div className="relative group">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => sheet.setShowOptimizeInput(!sheet.showOptimizeInput)}
                      disabled={sheet.isOptimizing || sheet.isEvolutionLocked}
                      className={cn(sheet.isEvolutionLocked && 'opacity-50 cursor-not-allowed')}
                    >
                      {sheet.isOptimizing ? (
                        <Loader2 className="animate-spin mr-2" size={16} />
                      ) : (
                        <Zap size={16} className="mr-2" />
                      )}
                      {t('detail.optimize')}
                    </Button>
                    {sheet.isEvolutionLocked && (
                      <div className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 hidden group-hover:block w-max max-w-[200px] px-2 py-1 bg-popover text-popover-foreground text-xs rounded border z-50 text-center pointer-events-none">
                        Unlock evolution to optimize
                      </div>
                    )}
                  </div>
                )}
              </div>
              {sheet.showOptimizeInput && (
                <div className="flex gap-2 mt-2">
                  <Input
                    placeholder={t('detail.optimizePlaceholder')}
                    value={sheet.optimizeInstruction}
                    onChange={(e) => sheet.setOptimizeInstruction(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && sheet.optimizeInstruction.trim()) {
                        sheet.handleOptimize();
                      }
                    }}
                    className="flex-1"
                  />
                  <Button
                    size="sm"
                    onClick={sheet.handleOptimize}
                    disabled={sheet.isOptimizing || !sheet.optimizeInstruction.trim()}
                  >
                    {sheet.isOptimizing && <Loader2 className="animate-spin mr-2" size={16} />}
                    {t('detail.optimizeSubmit')}
                  </Button>
                </div>
              )}
              <Button
                variant={isEnabled ? 'outline' : 'default'}
                size="sm"
                onClick={sheet.handleToggle}
                disabled={sheet.isToggling}
              >
                {sheet.isToggling && <Loader2 className="animate-spin mr-2" size={16} />}
                {isEnabled ? t('detail.disable') : t('detail.enable')}
              </Button>
            </div>
          </SheetContent>
        </Sheet>

        <AlertDialog open={sheet.showDeleteConfirm} onOpenChange={sheet.setShowDeleteConfirm}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>{t('detail.confirmDelete')}</AlertDialogTitle>
              <AlertDialogDescription>{t('detail.confirmDeleteDesc', { name: skill.name })}</AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>{t('upload.cancel')}</AlertDialogCancel>
              <AlertDialogAction
                onClick={sheet.handleDelete}
                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              >
                {sheet.isDeleting && <Loader2 className="animate-spin mr-2" size={16} />}
                {t('detail.delete')}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        <AlertDialog open={sheet.showTrustConfirm} onOpenChange={sheet.setShowTrustConfirm}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>{t('card.trustConfirmTitle')}</AlertDialogTitle>
              <AlertDialogDescription>{t('card.trustConfirmDesc', { name: skill.name })}</AlertDialogDescription>
            </AlertDialogHeader>
            {skill.security && (
              <div className="px-1">
                <SecurityScanSection security={skill.security} t={t} />
              </div>
            )}
            <AlertDialogFooter>
              <AlertDialogCancel>{t('upload.cancel')}</AlertDialogCancel>
              <AlertDialogAction onClick={sheet.handleTrust} className="bg-green-600 text-white hover:bg-green-700">
                {sheet.isTrusting && <Loader2 className="animate-spin mr-2" size={16} />}
                {t('card.trustSkill')}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        <SkillExportDialog skill={skill} open={sheet.showExportDialog} onOpenChange={sheet.setShowExportDialog} />
      </>
    );
  },
);

SkillDetailSheet.displayName = 'SkillDetailSheet';

export default SkillDetailSheet;
