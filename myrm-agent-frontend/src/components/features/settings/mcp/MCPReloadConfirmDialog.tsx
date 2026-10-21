'use client';

import { IconRefresh } from '@/components/features/icons/PremiumIcons';
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
import { useTranslations } from 'next-intl';

interface MCPReloadConfirmDialogProps {
  open: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function MCPReloadConfirmDialog({ open, onConfirm, onCancel }: MCPReloadConfirmDialogProps) {
  const t = useTranslations('settings');

  return (
    <AlertDialog open={open} onOpenChange={(value) => !value && onCancel()}>
      <AlertDialogContent className="max-w-md">
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <IconRefresh className="h-5 w-5 text-amber-500" />
            {t('mcpReloadConfirmTitle')}
          </AlertDialogTitle>
          <AlertDialogDescription>{t('mcpReloadConfirmDesc')}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={onCancel}>{t('mcpCancel')}</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm}>{t('mcpReloadConfirmAction')}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
