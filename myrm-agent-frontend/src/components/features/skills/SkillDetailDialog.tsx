'use client';

import { memo, useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { Calendar, Tag, Package, Trash2, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/primitives/dialog';
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
import { toast } from '@/hooks/useToast';
import { getSkillFile } from '@/services/skill';
import type { Skill } from '@/store/skill/types';
import { getCategoryIcon, getCategoryColor } from './skillCategories';

interface SkillDetailDialogProps {
  skill: Skill | null;
  open: boolean;
  isEnabled: boolean;
  showDeleteButton?: boolean;
  onOpenChange: (open: boolean) => void;
  onToggle?: (skillId: string) => Promise<void>;
  onDelete?: (skill: Skill) => Promise<void>;
}

const SkillDetailDialog = memo(
  ({ skill, open, isEnabled, showDeleteButton = false, onOpenChange, onToggle, onDelete }: SkillDetailDialogProps) => {
    const t = useTranslations('settings.skills');
    const [skillContent, setSkillContent] = useState<string>('');
    const [isLoadingContent, setIsLoadingContent] = useState(false);
    const [isToggling, setIsToggling] = useState(false);
    const [isDeleting, setIsDeleting] = useState(false);
    const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

    // 加载 SKILL.md 内容
    useEffect(() => {
      if (skill && open) {
        setIsLoadingContent(true);
        getSkillFile(skill.id, 'SKILL.md')
          .then(setSkillContent)
          .catch(() => setSkillContent(''))
          .finally(() => setIsLoadingContent(false));
      }
    }, [skill, open]);

    const handleToggle = useCallback(async () => {
      if (!skill || !onToggle) return;

      setIsToggling(true);
      try {
        await onToggle(skill.id);
        toast({
          title: isEnabled ? t('detail.disableSuccess') : t('detail.enableSuccess'),
          description: isEnabled
            ? t('detail.disableSuccessDesc', { name: skill.name })
            : t('detail.enableSuccessDesc', { name: skill.name }),
        });
      } catch {
        toast({
          title: t('detail.toggleFailed'),
          variant: 'destructive',
        });
      } finally {
        setIsToggling(false);
      }
    }, [skill, onToggle, isEnabled, t]);

    const handleDelete = useCallback(async () => {
      if (!skill || !onDelete) return;

      setIsDeleting(true);
      try {
        await onDelete(skill);
        toast({
          title: t('detail.deleteSuccess'),
          description: t('detail.deleteSuccessDesc', { name: skill.name }),
        });
        onOpenChange(false);
      } catch {
        toast({
          title: t('detail.deleteFailed'),
          variant: 'destructive',
        });
      } finally {
        setIsDeleting(false);
        setShowDeleteConfirm(false);
      }
    }, [skill, onDelete, onOpenChange, t]);

    if (!skill) return null;

    const category = skill.category || 'other';
    const CategoryIcon = getCategoryIcon(category);
    const categoryColor = getCategoryColor(category);

    return (
      <>
        <Dialog open={open} onOpenChange={onOpenChange}>
          <DialogContent className="max-w-2xl max-h-[85vh] flex flex-col p-0">
            <DialogHeader className="p-6 pb-4 border-b">
              <div className="flex items-start gap-4">
                {/* 图标 */}
                <div
                  className={cn('flex-shrink-0 w-12 h-12 rounded-xl flex items-center justify-center', categoryColor)}
                >
                  <CategoryIcon size={24} />
                </div>

                {/* 标题和元信息 */}
                <div className="flex-1 min-w-0 pr-8">
                  <DialogTitle className="text-xl font-semibold">{skill.name}</DialogTitle>
                  <div className="flex items-center gap-3 mt-2 text-sm text-muted-foreground">
                    <div className="flex items-center gap-1">
                      <Package size={14} />
                      <span>v{skill.version}</span>
                    </div>
                    <Badge variant="secondary" className={cn('text-xs', categoryColor)}>
                      {t(`categories.${category}` as const)}
                    </Badge>
                  </div>
                </div>
              </div>
            </DialogHeader>

            {/* 内容区域 */}
            <div className="flex-1 overflow-y-auto px-6">
              <div className="py-4 space-y-6">
                {/* 描述 */}
                <div>
                  <p className="text-muted-foreground">{skill.description}</p>
                </div>

                {/* 标签 */}
                {skill.tags.length > 0 && (
                  <div className="flex items-center gap-2 flex-wrap">
                    <Tag size={14} className="text-muted-foreground" />
                    {skill.tags.map((tag) => (
                      <Badge key={tag} variant="outline" className="text-xs">
                        {tag}
                      </Badge>
                    ))}
                  </div>
                )}

                {/* 时间信息 */}
                <div className="flex items-center gap-4 text-sm text-muted-foreground">
                  <div className="flex items-center gap-1">
                    <Calendar size={14} />
                    <span>
                      {t('card.createdAt')}: {new Date(skill.created_at).toLocaleDateString()}
                    </span>
                  </div>
                </div>

                {/* SKILL.md 内容 */}
                <div className="border rounded-lg bg-muted/30">
                  <div className="px-4 py-2 border-b bg-muted rounded-t-lg">
                    <span className="text-sm font-medium">SKILL.md</span>
                  </div>
                  <div className="p-4">
                    {isLoadingContent ? (
                      <div className="flex items-center justify-center py-8">
                        <Loader2 className="animate-spin text-muted-foreground" size={24} />
                      </div>
                    ) : skillContent ? (
                      <pre className="text-sm whitespace-pre-wrap font-mono text-muted-foreground">{skillContent}</pre>
                    ) : (
                      <p className="text-sm text-muted-foreground text-center py-4">{t('detail.loadFailed')}</p>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* 底部操作 */}
            <div className="p-6 pt-4 border-t flex items-center justify-between">
              {showDeleteButton && (
                <Button variant="destructive" onClick={() => setShowDeleteConfirm(true)} disabled={isDeleting}>
                  {isDeleting ? (
                    <Loader2 className="animate-spin mr-2" size={16} />
                  ) : (
                    <Trash2 size={16} className="mr-2" />
                  )}
                  {t('detail.delete')}
                </Button>
              )}

              <div className={cn('flex items-center gap-3', !showDeleteButton && 'ml-auto')}>
                <Button variant="outline" onClick={() => onOpenChange(false)}>
                  {t('detail.close')}
                </Button>
                <Button variant={isEnabled ? 'outline' : 'default'} onClick={handleToggle} disabled={isToggling}>
                  {isToggling && <Loader2 className="animate-spin mr-2" size={16} />}
                  {isEnabled ? t('detail.disable') : t('detail.enable')}
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>

        {/* 删除确认对话框 */}
        <AlertDialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>{t('detail.confirmDelete')}</AlertDialogTitle>
              <AlertDialogDescription>{t('detail.confirmDeleteDesc', { name: skill.name })}</AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>{t('upload.cancel')}</AlertDialogCancel>
              <AlertDialogAction
                onClick={handleDelete}
                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              >
                {isDeleting && <Loader2 className="animate-spin mr-2" size={16} />}
                {t('detail.delete')}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </>
    );
  },
);

SkillDetailDialog.displayName = 'SkillDetailDialog';

export default SkillDetailDialog;
