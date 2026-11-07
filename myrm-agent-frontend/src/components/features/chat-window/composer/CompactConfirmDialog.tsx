'use client';

/**
 * [INPUT]
 * - @/components/primitives/alert-dialog (POS: 确认对话框原语)
 *
 * [OUTPUT]
 * - CompactConfirmDialog: 手动压缩会话前的确认对话框。
 *
 * [POS]
 * 手动压缩会清除 Prompt Cache、可能抬高下一轮的成本，所以先确认（文案见 `chat.compact.confirmDescription`）；
 * 勾选「不再提醒」后由 useMessageInput 写入本机并在之后跳过本对话框。
 */
import { AlertTriangle } from 'lucide-react';
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

interface CompactConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  dontRemind: boolean;
  onDontRemindChange: (checked: boolean) => void;
  onConfirm: () => void;
}

export function CompactConfirmDialog({
  open,
  onOpenChange,
  dontRemind,
  onDontRemindChange,
  onConfirm,
}: CompactConfirmDialogProps) {
  const commonT = useTranslations('common');
  const chatT = useTranslations('chat');

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent className="sm:max-w-[425px]">
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2 text-amber-500">
            <AlertTriangle size={20} />
            {chatT('compact.confirmTitle')}
          </AlertDialogTitle>
          <AlertDialogDescription className="text-base pt-2">
            {chatT('compact.confirmDescription')}
          </AlertDialogDescription>
        </AlertDialogHeader>

        <div className="flex items-center space-x-2 py-2">
          <input
            type="checkbox"
            id="dontRemindCompact"
            checked={dontRemind}
            onChange={(e) => onDontRemindChange(e.target.checked)}
            className="h-4 w-4 text-primary border-gray-300 rounded focus:ring-primary"
          />
          <label htmlFor="dontRemindCompact" className="text-sm text-muted-foreground">
            {chatT('compact.dontRemindAgain')}
          </label>
        </div>

        <AlertDialogFooter>
          <AlertDialogCancel>{commonT('cancel')}</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm} className="bg-amber-500 text-white hover:bg-amber-600">
            {chatT('compact.confirmButton')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
