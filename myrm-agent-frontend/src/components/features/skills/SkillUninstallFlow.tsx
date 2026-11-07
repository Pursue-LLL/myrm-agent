'use client';

/**
 * [INPUT] @/hooks/agent/useSkillDiscovery::uninstall (POS: 卸载请求), @/lib/api::ApiError (POS: 409 依赖冲突识别)
 * [OUTPUT] useSkillUninstall: 卸载确认、依赖冲突后的强制卸载确认与结果提示; SkillUninstallDialogs: 两个确认对话框
 * [POS] SkillDiscoverTab 的卸载流程；卸载走 canonical installed_skill_id，被其它技能依赖（409）时先列出依赖再确认强制卸载。
 */

import { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Trash2 } from 'lucide-react';
import { toast } from '@/hooks/shared/useToast';
import { ApiError } from '@/lib/api';
import type { DiscoverySearchResult } from '@/services/skill';
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

interface ForceUninstallTarget {
  skillId: string;
  name: string;
  dependents: string[];
}

interface UseSkillUninstallParams {
  uninstall: (skillId: string, force?: boolean) => Promise<boolean>;
  onInstalled?: () => void;
}

export interface SkillUninstallDialogsProps {
  uninstallOpen: boolean;
  pendingUninstall: Pick<DiscoverySearchResult, 'name'> | null;
  forceUninstallSkill: ForceUninstallTarget | null;
  onConfirmUninstall: () => void;
  onConfirmForceUninstall: () => void;
  onDismissUninstall: () => void;
  onDismissForceUninstall: () => void;
}

export function useSkillUninstall({ uninstall, onInstalled }: UseSkillUninstallParams) {
  const t = useTranslations('settings.skills.discover');
  const [uninstallDialogOpen, setUninstallDialogOpen] = useState(false);
  const [pendingUninstall, setPendingUninstall] = useState<DiscoverySearchResult | null>(null);
  const [forceUninstallSkill, setForceUninstallSkill] = useState<ForceUninstallTarget | null>(null);

  const requestUninstall = useCallback((skill: DiscoverySearchResult) => {
    setPendingUninstall(skill);
    setUninstallDialogOpen(true);
  }, []);

  const handleConfirmUninstall = useCallback(async () => {
    setUninstallDialogOpen(false);
    if (!pendingUninstall) {
      return;
    }

    const skillId = pendingUninstall.installed_skill_id;
    if (!skillId) {
      toast({ title: t('uninstallFailed'), variant: 'destructive' });
      setPendingUninstall(null);
      return;
    }
    try {
      const success = await uninstall(skillId);
      if (success) {
        toast({ title: `${t('uninstalled')} ${pendingUninstall.name}` });
        onInstalled?.();
      } else {
        toast({ title: t('uninstallFailed'), variant: 'destructive' });
      }
    } catch (error) {
      if (error instanceof ApiError && error.code === 409) {
        const dependents = Array.isArray(error.data?.impacted_dependents)
          ? (error.data.impacted_dependents as string[])
          : [];
        setForceUninstallSkill({
          skillId,
          name: pendingUninstall.name,
          dependents,
        });
      } else {
        toast({
          title: t('uninstallFailed'),
          description: error instanceof Error ? error.message : undefined,
          variant: 'destructive',
        });
      }
    }
    setPendingUninstall(null);
  }, [pendingUninstall, uninstall, t, onInstalled]);

  const handleConfirmForceUninstall = useCallback(async () => {
    if (!forceUninstallSkill) {
      return;
    }
    const { skillId, name } = forceUninstallSkill;
    setForceUninstallSkill(null);
    try {
      const success = await uninstall(skillId, true);
      if (success) {
        toast({ title: `${t('uninstalled')} ${name}` });
        onInstalled?.();
      } else {
        toast({ title: t('uninstallFailed'), variant: 'destructive' });
      }
    } catch {
      toast({ title: t('uninstallFailed'), variant: 'destructive' });
    }
  }, [forceUninstallSkill, uninstall, t, onInstalled]);

  const dismissUninstall = useCallback(() => {
    setUninstallDialogOpen(false);
    setPendingUninstall(null);
  }, []);
  const dismissForceUninstall = useCallback(() => setForceUninstallSkill(null), []);

  const dialogProps: SkillUninstallDialogsProps = {
    uninstallOpen: uninstallDialogOpen,
    pendingUninstall,
    forceUninstallSkill,
    onConfirmUninstall: handleConfirmUninstall,
    onConfirmForceUninstall: handleConfirmForceUninstall,
    onDismissUninstall: dismissUninstall,
    onDismissForceUninstall: dismissForceUninstall,
  };

  return { requestUninstall, dialogProps };
}

export function SkillUninstallDialogs({
  uninstallOpen,
  pendingUninstall,
  forceUninstallSkill,
  onConfirmUninstall,
  onConfirmForceUninstall,
  onDismissUninstall,
  onDismissForceUninstall,
}: SkillUninstallDialogsProps) {
  const t = useTranslations('settings.skills.discover');

  return (
    <>
      <AlertDialog open={uninstallOpen} onOpenChange={(v) => !v && onDismissUninstall()}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <Trash2 className="h-5 w-5 text-destructive-text" />
              {t('uninstall')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('uninstallConfirm')}
              {pendingUninstall && <span className="font-medium text-foreground"> {pendingUninstall.name}</span>}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('scanCancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={onConfirmUninstall}
              className="bg-destructive hover:bg-destructive/90 text-destructive-foreground"
            >
              <Trash2 className="h-4 w-4 mr-1.5" />
              {t('uninstall')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={forceUninstallSkill !== null} onOpenChange={(v) => !v && onDismissForceUninstall()}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <Trash2 className="h-5 w-5 text-destructive-text" />
              {t('forceUninstallTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('forceUninstallDesc', {
                name: forceUninstallSkill?.name ?? '',
                count: String(forceUninstallSkill?.dependents.length ?? 0),
              })}
            </AlertDialogDescription>
            {forceUninstallSkill && forceUninstallSkill.dependents.length > 0 && (
              <div className="mt-2 max-h-32 overflow-y-auto rounded-lg border bg-muted/40 p-2">
                <ul className="space-y-1">
                  {forceUninstallSkill.dependents.map((dep) => (
                    <li key={dep} className="truncate text-sm text-foreground">
                      {dep}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('scanCancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={onConfirmForceUninstall}
              className="bg-destructive hover:bg-destructive/90 text-destructive-foreground"
            >
              <Trash2 className="h-4 w-4 mr-1.5" />
              {t('forceUninstall')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
