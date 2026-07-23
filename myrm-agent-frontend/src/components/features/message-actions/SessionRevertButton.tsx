'use client';

import { RotateCcw, Check } from 'lucide-react';
import { useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { apiRequest } from '@/lib/api';
import { ConfirmDialog } from '@/components/features/app-shell/confirm-dialog';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/primitives/tooltip';
import { toast } from '@/hooks/useToast';

interface FileChangeInfo {
  path: string;
  operation: string;
  has_original: boolean;
  timestamp: number;
  revertible?: boolean;
  skip_reason?: string | null;
}

interface RevertResponse {
  success: boolean;
  reverted_files: string[];
  warnings: string[];
  skipped_files: string[];
}

interface SessionRevertButtonProps {
  sessionId: string;
}

export default function SessionRevertButton({ sessionId }: SessionRevertButtonProps) {
  const t = useTranslations('messageActions');
  const [status, setStatus] = useState<'idle' | 'loading' | 'success'>('idle');
  const [fileCount, setFileCount] = useState(0);
  const [skippedCount, setSkippedCount] = useState(0);
  const [showConfirm, setShowConfirm] = useState(false);

  const handleClick = useCallback(async () => {
    setStatus('loading');
    try {
      const data = (await apiRequest(`/files/revert/changes/${sessionId}`)) as Record<
        string,
        FileChangeInfo[]
      >;
      const revertiblePaths = new Set<string>();
      const nonRevertiblePaths = new Set<string>();
      for (const changes of Object.values(data)) {
        for (const c of changes) {
          if (c.revertible === false) {
            nonRevertiblePaths.add(c.path);
          } else {
            revertiblePaths.add(c.path);
          }
        }
      }

      if (revertiblePaths.size === 0 && nonRevertiblePaths.size === 0) {
        toast({ title: t('revertSessionEmpty'), variant: 'default' });
        return;
      }

      if (revertiblePaths.size === 0) {
        toast({ title: t('revertSessionNotRevertible'), variant: 'default' });
        return;
      }

      setFileCount(revertiblePaths.size);
      setSkippedCount(nonRevertiblePaths.size);
      setShowConfirm(true);
    } catch {
      toast({ title: t('revertSessionFetchError'), variant: 'destructive' });
    } finally {
      setStatus('idle');
    }
  }, [sessionId, t]);

  const handleConfirm = useCallback(async () => {
    try {
      const result = (await apiRequest('/files/revert/session', {
        method: 'POST',
        body: JSON.stringify({ session_id: sessionId }),
      })) as RevertResponse;

      setShowConfirm(false);

      if (result.reverted_files.length > 0) {
        setStatus('success');
        window.dispatchEvent(new CustomEvent('app_resync_required'));
        const skippedTotal =
          result.skipped_files.length > 0 ? result.skipped_files.length : skippedCount;
        toast({
          title:
            skippedTotal > 0
              ? t('revertSessionSuccessPartial', {
                  count: result.reverted_files.length,
                  skipped: skippedTotal,
                })
              : t('revertSessionSuccess'),
          variant: 'default',
        });
        setTimeout(() => setStatus('idle'), 2000);
        return;
      }

      toast({ title: t('revertSessionNotRevertible'), variant: 'default' });
      setStatus('idle');
    } catch {
      setShowConfirm(false);
      toast({ title: t('revertSessionFetchError'), variant: 'destructive' });
      setStatus('idle');
    }
  }, [sessionId, skippedCount, t]);

  const chipClassName =
    'inline-flex items-center justify-center rounded-full border border-border/70 bg-muted/40 p-1.5 text-muted-foreground transition-colors hover:border-primary/30 hover:text-foreground disabled:opacity-60';

  if (status === 'success') {
    return (
      <span
        className={`${chipClassName} border-emerald-500/40 text-emerald-600 dark:text-emerald-400`}
        aria-label={t('revertSessionSuccess')}
      >
        <Check size={16} />
      </span>
    );
  }

  return (
    <>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            data-testid="session-revert-button"
            onClick={handleClick}
            disabled={status === 'loading'}
            className={chipClassName}
            aria-label={t('revertSession')}
          >
            <RotateCcw size={16} className={status === 'loading' ? 'animate-spin' : undefined} />
          </button>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="max-w-xs text-xs">
          {t('revertSession')}
        </TooltipContent>
      </Tooltip>

      <ConfirmDialog
        open={showConfirm}
        onOpenChange={setShowConfirm}
        title={t('revertSession')}
        description={
          skippedCount > 0
            ? t('revertSessionDescPartial', { count: fileCount, skipped: skippedCount })
            : t('revertSessionDesc', { count: fileCount })
        }
        confirmText={t('revertSessionConfirm')}
        cancelText={t('cancel')}
        variant="warning"
        onConfirm={handleConfirm}
      />
    </>
  );
}
