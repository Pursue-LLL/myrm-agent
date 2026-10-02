/**
 * [INPUT]
 * - `@/components/primitives/alert-dialog` (POS: 确认对话框基础件)
 * - `next-intl` (`settings.system.serverConnection.activeSessionsDialog`)
 *
 * [OUTPUT]
 * - `ActiveSessionsSwitchConfirmDialog`: 本地→远程切换前的活跃会话确认对话框。
 *
 * [POS]
 * 切换连接前发现本地活跃生成会话时弹出，用户知情确认后才执行切换
 * （切换会等待活跃会话完成并断开本地流）。父组件持有开关与回调，本组件无状态副作用。
 */

'use client';

import { useTranslations } from 'next-intl';
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
import { IconAlertCircle } from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';

interface ActiveSessionsSwitchConfirmDialogProps {
  open: boolean;
  count: number;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ActiveSessionsSwitchConfirmDialog({
  open,
  count,
  onConfirm,
  onCancel,
}: ActiveSessionsSwitchConfirmDialogProps) {
  const t = useTranslations('settings.system.serverConnection.activeSessionsDialog');

  return (
    <AlertDialog open={open} onOpenChange={(next) => (next ? undefined : onCancel())}>
      <AlertDialogContent className="max-w-md">
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2 text-base">
            <IconAlertCircle className="h-5 w-5 text-amber-500" aria-hidden />
            {t('title')}
          </AlertDialogTitle>
          <AlertDialogDescription>
            {t('description', { count })}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel
            onClick={onCancel}
            className="border border-white/10 hover:bg-white/5"
          >
            {t('cancel')}
          </AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            className={cn('bg-indigo-500 text-white hover:bg-indigo-600')}
          >
            {t('confirm')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
