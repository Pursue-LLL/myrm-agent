import { useTranslations } from 'next-intl';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';

interface LinkDetectionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  dontRemindAgain: boolean;
  setDontRemindAgain: (checked: boolean) => void;
  onAddAtSymbol: () => void;
  onSkip: () => void;
}

/**
 * 链接检测对话框
 * 当用户输入链接时，提示是否添加@符号
 */
export const LinkDetectionDialog = ({
  open,
  onOpenChange,
  dontRemindAgain,
  setDontRemindAgain,
  onAddAtSymbol,
  onSkip,
}: LinkDetectionDialogProps) => {
  const t = useTranslations('chat');
  const commonT = useTranslations('common');

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>{t('linkDetected')}</DialogTitle>
          <DialogDescription>{t('linkDetectedDescription')}</DialogDescription>
        </DialogHeader>

        {/* 不再提醒复选框 */}
        <div className="flex items-center space-x-2 py-2">
          <input
            type="checkbox"
            id="dontRemindAgain"
            checked={dontRemindAgain}
            onChange={(e) => setDontRemindAgain(e.target.checked)}
            className="h-4 w-4 text-primary border-gray-300 rounded focus:ring-primary"
          />
          <label htmlFor="dontRemindAgain" className="text-sm text-gray-700 dark:text-gray-300">
            {t('dontRemindAgain')}
          </label>
        </div>

        <DialogFooter>
          <button
            onClick={onSkip}
            className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-full transition-colors"
          >
            {commonT('no')}
          </button>
          <button
            onClick={onAddAtSymbol}
            className="px-4 py-2 text-sm font-medium text-white bg-primary hover:bg-primary-hover rounded-full transition-colors"
          >
            {commonT('yes')}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
