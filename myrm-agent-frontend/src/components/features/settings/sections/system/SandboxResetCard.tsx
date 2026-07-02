'use client';

import { memo, useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { RefreshCw, HardDrive, AlertTriangle } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from '@/lib/utils/toast';
import { apiRequest } from '@/lib/api';
import { ConfirmDialog } from '@/components/features/app-shell/confirm-dialog';

interface RecreateResponse {
  status: string;
  message: string;
}

const SandboxResetCard = memo(() => {
  const t = useTranslations('settings.system.sandboxReset');
  const [isResetting, setIsResetting] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  const handleReset = useCallback(async () => {
    setIsResetting(true);
    try {
      const resp = await apiRequest<RecreateResponse>('/system/sandbox/recreate', {
        method: 'POST',
      });
      toast.success(resp.message || t('success'));
    } catch {
      toast.error(t('failed'));
    } finally {
      setIsResetting(false);
      setShowConfirm(false);
    }
  }, [t]);

  return (
    <section className="space-y-6">
      <div className="flex items-center gap-3 px-2">
        <HardDrive className="w-5 h-5 text-muted-foreground" />
        <h2 className="text-sm font-black uppercase tracking-[0.2em] text-muted-foreground/70">
          {t('title')}
        </h2>
      </div>

      <div className="p-8 rounded-[2.5rem] bg-white/5 border border-white/10 space-y-6">
        <div className="flex items-start gap-4">
          <div className="p-3 rounded-2xl bg-amber-500/10 border border-amber-500/20 flex-shrink-0">
            <AlertTriangle className="w-6 h-6 text-amber-500" />
          </div>
          <div className="flex-1 space-y-2">
            <h3 className="text-base font-bold text-foreground">{t('title')}</h3>
            <p className="text-sm text-muted-foreground leading-relaxed">{t('description')}</p>
          </div>
        </div>

        <div className="h-px bg-white/5" />

        <div className="flex items-center justify-between">
          <div className="space-y-1">
            <p className="text-xs text-muted-foreground/70">{t('preserved')}</p>
            <p className="text-xs text-muted-foreground/70">{t('reset')}</p>
          </div>

          <ConfirmDialog
            open={showConfirm}
            onOpenChange={setShowConfirm}
            title={t('confirmTitle')}
            description={t('confirmDescription')}
            confirmText={t('confirm')}
            cancelText={t('cancel')}
            loadingText={t('resetting')}
            variant="warning"
            onConfirm={handleReset}
            trigger={
              <button
                disabled={isResetting}
                className={cn(
                  'flex items-center gap-2 px-5 py-2.5 rounded-xl font-bold text-sm transition-all border',
                  'bg-amber-500/10 text-amber-500 border-amber-500/20 hover:bg-amber-500/20',
                  'disabled:opacity-50 disabled:cursor-not-allowed',
                )}
              >
                <RefreshCw className={cn('w-4 h-4', isResetting && 'animate-spin')} />
                {t('button')}
              </button>
            }
          />
        </div>
      </div>
    </section>
  );
});

SandboxResetCard.displayName = 'SandboxResetCard';

export default SandboxResetCard;
