'use client';

import { cn } from '@/lib/utils/classnameUtils';
import { useTranslations } from 'next-intl';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/primitives/alert-dialog';
import { Button } from '@/components/primitives/button';
import useChatStore from '@/store/useChatStore';
import { apiRequest } from '@/lib/api';
import { toast } from '@/lib/utils/toast';
import { useState } from 'react';

const SandboxIcon = ({ className }: { className?: string }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width="14"
    height="14"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.8"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={cn('shrink-0', className)}
  >
    <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
    <polyline points="7.5 4.21 12 6.81 16.5 4.21" />
    <polyline points="7.5 19.79 7.5 14.6 3 12" />
    <polyline points="21 12 16.5 14.6 16.5 19.79" />
    <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
    <line x1="12" y1="22.08" x2="12" y2="12" />
  </svg>
);

const SandboxModeToggle = () => {
  const t = useTranslations('sandbox');
  const sandboxMode = useChatStore((s) => s.sandboxMode);
  const setSandboxMode = useChatStore((s) => s.setSandboxMode);
  const actionMode = useChatStore((s) => s.actionMode);
  const chatId = useChatStore((s) => s.chatId);
  const [loading, setLoading] = useState(false);
  const [showExitDialog, setShowExitDialog] = useState(false);

  if (actionMode !== 'agent') return null;

  const handleEnable = async () => {
    if (!chatId) {
      setSandboxMode(true);
      return;
    }
    setLoading(true);
    try {
      await apiRequest(`/chats/${chatId}/sandbox/enable`, { method: 'POST' });
      setSandboxMode(true);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t('enableSandbox');
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  const handleMerge = async () => {
    if (!chatId) return;
    setLoading(true);
    setShowExitDialog(false);
    try {
      const res = await apiRequest<{ success: boolean; message: string }>(
        `/chats/${chatId}/sandbox/merge`,
        { method: 'POST' },
      );
      if (res?.success) {
        setSandboxMode(false);
        toast.success(t('mergeSuccess'));
      } else {
        toast.error(res?.message || t('mergeFailed'));
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t('mergeFailed');
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  const handleDiscard = async () => {
    if (!chatId) {
      setSandboxMode(false);
      setShowExitDialog(false);
      return;
    }
    setLoading(true);
    setShowExitDialog(false);
    try {
      await apiRequest(`/chats/${chatId}/sandbox/disable`, { method: 'POST' });
      setSandboxMode(false);
      toast.success(t('discardSuccess'));
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t('disableSandbox');
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  const toggle = () => {
    if (loading) return;
    if (sandboxMode) {
      setShowExitDialog(true);
    } else {
      handleEnable();
    }
  };

  return (
    <>
      <TooltipProvider delayDuration={200}>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              aria-label={t('sandboxMode')}
              aria-pressed={sandboxMode}
              disabled={loading}
              onClick={toggle}
              className={cn(
                'relative flex shrink-0 items-center gap-1.5 h-7 px-2.5 rounded-full text-xs font-medium whitespace-nowrap transition-all duration-300 cursor-pointer select-none',
                sandboxMode
                  ? 'bg-primary/10 dark:bg-primary/15 text-primary border border-primary/30 dark:border-primary/25'
                  : 'bg-black/[0.04] dark:bg-white/[0.06] text-black/40 dark:text-white/40 border border-transparent hover:text-black dark:hover:text-white hover:bg-black/[0.08] dark:hover:bg-white/[0.1]',
                loading && 'opacity-60 pointer-events-none',
              )}
            >
              <SandboxIcon
                className={cn(
                  'transition-colors duration-300',
                  sandboxMode ? 'text-primary' : 'text-current',
                )}
              />
              <span className="hidden xl:inline">{t('sandboxMode')}</span>
            </button>
          </TooltipTrigger>
          <TooltipContent side="top" className="max-w-64 p-3">
            <p className="font-semibold text-sm mb-1">{t('sandboxMode')}</p>
            <p className="text-xs text-muted-foreground leading-relaxed">{t('sandboxModeDesc')}</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>

      <AlertDialog open={showExitDialog} onOpenChange={setShowExitDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('disableSandbox')}</AlertDialogTitle>
            <AlertDialogDescription>{t('sandboxModeDesc')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <Button variant="outline" onClick={() => setShowExitDialog(false)}>
              {t('active')}
            </Button>
            <Button variant="destructive" onClick={handleDiscard}>
              {t('discardSandbox')}
            </Button>
            <Button onClick={handleMerge}>
              {t('mergeSandbox')}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
};

export default SandboxModeToggle;
