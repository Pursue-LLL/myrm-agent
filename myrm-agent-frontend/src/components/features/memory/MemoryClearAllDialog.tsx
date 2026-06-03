'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { Loader2 } from 'lucide-react';

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import { cn } from '@/lib/utils/classnameUtils';

interface MemoryClearAllDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  isClearing: boolean;
  onConfirm: () => void;
}

const MemoryClearAllDialog = memo<MemoryClearAllDialogProps>(({ open, onOpenChange, isClearing, onConfirm }) => {
  const t = useTranslations('memory');
  const tCommon = useTranslations('common');

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[400px]">
        <DialogHeader>
          <DialogTitle className="text-destructive">{t('clearAllTitle')}</DialogTitle>
          <DialogDescription>{t('clearAllDescription')}</DialogDescription>
        </DialogHeader>
        <DialogFooter className="gap-2 sm:gap-0">
          <button
            onClick={() => onOpenChange(false)}
            disabled={isClearing}
            className={cn(
              'rounded-lg px-4 py-2 text-sm font-medium transition-colors',
              'border border-border/50 hover:bg-accent',
            )}
          >
            {tCommon('cancel')}
          </button>
          <button
            onClick={onConfirm}
            disabled={isClearing}
            className={cn(
              'rounded-lg px-4 py-2 text-sm font-medium transition-colors',
              'bg-destructive text-destructive-foreground hover:bg-destructive/90',
              'disabled:cursor-not-allowed disabled:opacity-50',
            )}
          >
            {isClearing ? <Loader2 size={14} className="animate-spin" /> : t('clearAllConfirm')}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
});

MemoryClearAllDialog.displayName = 'MemoryClearAllDialog';

export default MemoryClearAllDialog;
