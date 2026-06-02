'use client';

import { memo, useEffect, useState } from 'react';
import { useTranslations, useLocale } from 'next-intl';
import { AlertCircle, CheckCircle2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useRouter } from 'next/navigation';

interface ConfigError {
  error_type: string;
  messages?: {
    en: string;
    zh: string;
  };
  technical_details?: string;
  resolution_steps?: string[];
}

interface ProviderConfigErrorDialogProps {
  error: ConfigError | null;
  onClose: () => void;
}

const ProviderConfigErrorDialog = memo<ProviderConfigErrorDialogProps>(({ error, onClose }) => {
  const t = useTranslations('errors.configIncomplete');
  const locale = useLocale();
  const router = useRouter();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    setOpen(!!error);
  }, [error]);

  if (!error || error.error_type !== 'provider_not_configured') {
    return null;
  }

  const message = error.messages?.[locale as 'en' | 'zh'] || error.messages?.['en'] || '';
  const steps = error.resolution_steps || [];

  const handleConfigure = () => {
    router.push('/settings/models');
    setOpen(false);
    onClose();
  };

  const handleClose = (isOpen: boolean) => {
    setOpen(isOpen);
    if (!isOpen) {
      onClose();
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertCircle className="w-5 h-5 text-yellow-500" />
            {t('title')}
          </DialogTitle>
          <DialogDescription>{message}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <h4 className="text-sm font-semibold mb-2 flex items-center gap-1">{t('nextSteps')}</h4>
            <ul className="space-y-2">
              {steps.slice(0, 4).map((step, i) => (
                <li key={i} className="flex items-start gap-2 text-sm">
                  <CheckCircle2 className="w-4 h-4 mt-0.5 text-muted-foreground flex-shrink-0" />
                  <span>{step}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => handleClose(false)}>
            {t('skipForNow')}
          </Button>
          <Button onClick={handleConfigure}>{t('configureNow')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
});

ProviderConfigErrorDialog.displayName = 'ProviderConfigErrorDialog';

export default ProviderConfigErrorDialog;
