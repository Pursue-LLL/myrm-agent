'use client';

/**
 * [INPUT] @/components/primitives/alert-dialog (POS: Radix AlertDialog 封装), next-intl (POS: 取消按钮文案)
 * [OUTPUT] BatchConfirmAlert: 触发元素 + 二次确认弹窗（标题、说明、取消、确认），开合由弹窗自身管理
 * [POS] BatchDirectory 列表页与详情页所有二次确认共用的弹窗壳；危险操作的确认按钮使用实心 destructive 填充。
 */

import type { ReactElement } from 'react';
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
  AlertDialogTrigger,
} from '@/components/primitives/alert-dialog';

interface BatchConfirmAlertProps {
  trigger: ReactElement;
  title: string;
  description: string;
  confirmLabel: string;
  onConfirm: () => void;
  destructive?: boolean;
}

export function BatchConfirmAlert({
  trigger,
  title,
  description,
  confirmLabel,
  onConfirm,
  destructive = false,
}: BatchConfirmAlertProps) {
  const t = useTranslations('batchDirectory');
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>{trigger}</AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t('cancelButton')}</AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            className={destructive ? 'bg-destructive text-destructive-foreground' : undefined}
          >
            {confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
