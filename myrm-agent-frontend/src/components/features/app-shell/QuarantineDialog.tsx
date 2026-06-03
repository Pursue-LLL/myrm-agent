'use client';

import { useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { useQuarantineCheck } from '@/hooks/useQuarantineCheck';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import { ShieldAlert, Loader2, CheckCircle2 } from 'lucide-react';
import { useTranslations } from 'next-intl';

export function QuarantineDialog() {
  const t = useTranslations('quarantineDialog');
  const { isQuarantined } = useQuarantineCheck();
  const [isFixing, setIsFixing] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  const handleFix = async () => {
    setIsFixing(true);
    setErrorMsg('');
    try {
      const success = await invoke<boolean>('fix_quarantine_with_auth');
      if (success) {
        setIsSuccess(true);
        // 修复成功后，提示用户应用即将重启
        setTimeout(() => {
          invoke('restart_app').catch(console.error);
        }, 2000);
      } else {
        setErrorMsg(t('fixFailed'));
      }
    } catch (err: any) {
      console.error('Failed to fix quarantine:', err);
      setErrorMsg(err.toString() || t('fixFailedAuth'));
    } finally {
      setIsFixing(false);
    }
  };

  return (
    <Dialog open={isQuarantined && !isSuccess} onOpenChange={() => {}}>
      <DialogContent
        className="sm:max-w-[425px]"
        onPointerDownOutside={(e) => e.preventDefault()}
        onEscapeKeyDown={(e) => e.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-destructive">
            <ShieldAlert className="h-5 w-5" />
            {t('title')}
          </DialogTitle>
          <DialogDescription className="pt-4 text-base" dangerouslySetInnerHTML={{ __html: t('description') }} />
        </DialogHeader>

        {errorMsg && <div className="text-sm text-destructive bg-destructive/10 p-3 rounded-full">{errorMsg}</div>}

        {isSuccess && (
          <div className="flex items-center gap-2 text-sm text-green-600 bg-green-50 p-3 rounded-full">
            <CheckCircle2 className="h-4 w-4" />
            {t('fixSuccess')}
          </div>
        )}

        <DialogFooter className="mt-4">
          <Button onClick={handleFix} disabled={isFixing || isSuccess} className="w-full sm:w-auto">
            {isFixing ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                {t('btnFixing')}
              </>
            ) : isSuccess ? (
              t('btnSuccess')
            ) : (
              t('btnFix')
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
