'use client';

import { RotateCcw, Check, AlertCircle } from 'lucide-react';
import { useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { apiRequest } from '@/lib/api';
import { ConfirmDialog } from '@/components/features/app-shell/confirm-dialog';
import { toast } from '@/hooks/useToast';

interface FileChangeInfo {
  path: string;
  operation: string;
  has_original: boolean;
  timestamp: number;
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
  const [showConfirm, setShowConfirm] = useState(false);

  const handleClick = useCallback(async () => {
    setStatus('loading');
    try {
      const data = (await apiRequest(`/files/revert/changes/${sessionId}`)) as Record<
        string,
        FileChangeInfo[]
      >;
      const uniquePaths = new Set<string>();
      for (const changes of Object.values(data)) {
        for (const c of changes) {
          uniquePaths.add(c.path);
        }
      }

      if (uniquePaths.size === 0) {
        toast({ description: t('revertSessionEmpty'), variant: 'default' });
        setStatus('idle');
        return;
      }

      setFileCount(uniquePaths.size);
      setShowConfirm(true);
    } catch {
      toast({ description: t('revertSessionEmpty'), variant: 'destructive' });
    }
    setStatus('idle');
  }, [sessionId, t]);

  const handleConfirm = useCallback(async () => {
    const result = (await apiRequest('/files/revert/session', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId }),
    })) as RevertResponse;

    if (result.reverted_files.length > 0) {
      setStatus('success');
      window.dispatchEvent(new CustomEvent('app_resync_required'));
      toast({ description: t('revertSessionSuccess'), variant: 'default' });
      setTimeout(() => setStatus('idle'), 2000);
    }
  }, [sessionId, t]);

  if (status === 'success') {
    return (
      <span className="p-2.5 text-emerald-600 dark:text-emerald-400">
        <Check size={18} />
      </span>
    );
  }

  return (
    <>
      <button
        type="button"
        onClick={handleClick}
        disabled={status === 'loading'}
        className="p-2.5 rounded-full text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
        title={t('revertSession')}
        aria-label={t('revertSession')}
      >
        <RotateCcw size={18} className={status === 'loading' ? 'animate-spin' : ''} />
      </button>

      <ConfirmDialog
        open={showConfirm}
        onOpenChange={setShowConfirm}
        title={t('revertSession')}
        description={t('revertSessionDesc', { count: fileCount })}
        confirmText={t('revertSessionConfirm')}
        cancelText={t('cancel')}
        variant="warning"
        onConfirm={handleConfirm}
      />
    </>
  );
}
