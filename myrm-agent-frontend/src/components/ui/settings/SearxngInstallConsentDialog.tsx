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
} from '@/components/ui/alert-dialog';
import { IconLoader } from '@/components/ui/icons/PremiumIcons';

type SearxngInstallConsentDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void | Promise<void>;
  loading?: boolean;
};

export default function SearxngInstallConsentDialog({
  open,
  onOpenChange,
  onConfirm,
  loading = false,
}: SearxngInstallConsentDialogProps) {
  const t = useTranslations('settings.searchService.searxngInstall');

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('title')}</AlertDialogTitle>
          <AlertDialogDescription className="space-y-2 text-left">
            <p>{t('description')}</p>
            <ul className="list-disc pl-5 text-sm text-muted-foreground">
              <li>{t('stepDocker')}</li>
              <li>{t('stepConfigure')}</li>
              <li>{t('stepEnable')}</li>
            </ul>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={loading}>{t('cancel')}</AlertDialogCancel>
          <AlertDialogAction
            disabled={loading}
            onClick={(e) => {
              e.preventDefault();
              void onConfirm();
            }}
          >
            {loading ? <IconLoader className="mr-2 h-4 w-4 animate-spin" /> : null}
            {loading ? t('installing') : t('confirm')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
