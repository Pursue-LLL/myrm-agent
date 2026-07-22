'use client';

import { Undo2, Check, AlertCircle, ChevronDown, ChevronRight } from 'lucide-react';
import { useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { createPatch } from 'diff';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';
import { Button } from '@/components/primitives/button';
import { IconTrash, IconUndo } from '@/components/features/icons/PremiumIcons';
import { DiffViewer } from '@/lib/diff/DiffViewer';
import { cn } from '@/lib/utils/classnameUtils';
import { getAuthHeaders } from '@/lib/utils/authHeaders';
import { toast } from '@/hooks/useToast';

interface FileChange {
  path: string;
  operation: string;
  has_original: boolean;
  timestamp: number;
  revertible?: boolean;
  skip_reason?: string | null;
}

interface FileDiffItem {
  path: string;
  operation: string;
  original: string | null;
  current: string | null;
  isBinary: boolean;
}

interface RevertFilesProps {
  chatId: string;
  messageId: string;
}

function buildUnifiedDiff(item: FileDiffItem): string | null {
  if (item.isBinary || item.original === null) {
    return null;
  }
  const filename = item.path.split('/').pop() || item.path;
  return createPatch(filename, item.original ?? '', item.current ?? '', '', '', { context: 3 });
}

const RevertFiles = ({ chatId, messageId }: RevertFilesProps) => {
  const t = useTranslations('messageActions');
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [changes, setChanges] = useState<FileChange[] | null>(null);
  const [diffs, setDiffs] = useState<FileDiffItem[] | null>(null);
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(new Set());
  const [popoverOpen, setPopoverOpen] = useState(false);
  const [triggerLoading, setTriggerLoading] = useState(false);

  const fetchChanges = useCallback(async (): Promise<FileChange[] | 'error'> => {
    try {
      const res = await fetch(`/api/v1/files/revert/changes/${chatId}/${messageId}`, {
        headers: getAuthHeaders(),
      });
      if (!res.ok) return 'error';
      const data: FileChange[] = await res.json();
      return data.length > 0 ? data : [];
    } catch {
      return 'error';
    }
  }, [chatId, messageId]);

  const fetchDiffs = useCallback(async () => {
    try {
      const res = await fetch(`/api/v1/files/revert/diff/${chatId}/${messageId}`, {
        headers: getAuthHeaders(),
      });
      if (!res.ok) return null;
      const data: FileDiffItem[] = await res.json();
      return data.length > 0 ? data : null;
    } catch {
      return null;
    }
  }, [chatId, messageId]);

  const toggleExpanded = useCallback((path: string) => {
    setExpandedPaths((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }, []);

  const resetState = useCallback(() => {
    setStatus('idle');
    setChanges(null);
    setDiffs(null);
    setExpandedPaths(new Set());
    setPopoverOpen(false);
  }, []);

  const resolveNonRevertibleToast = useCallback(
    (changes: FileChange[]) => {
      const reason = changes.find((c) => c.skip_reason)?.skip_reason;
      if (reason === 'file_too_large') {
        return t('revertMessageNotRevertibleFileTooLarge');
      }
      if (reason === 'store_full') {
        return t('revertMessageNotRevertibleStoreFull');
      }
      return t('revertMessageNotRevertible');
    },
    [t],
  );

  const handleTriggerClick = useCallback(async () => {
    if (triggerLoading) return;
    setTriggerLoading(true);
    try {
      const [fileChanges, fileDiffs] = await Promise.all([fetchChanges(), fetchDiffs()]);
      if (fileChanges === 'error') {
        toast({ title: t('revertMessageFetchError'), variant: 'destructive' });
        return;
      }
      if (fileChanges.length === 0) {
        toast({ title: t('revertMessageEmpty'), variant: 'default' });
        return;
      }
      const revertibleChanges = fileChanges.filter((c) => c.revertible !== false);
      if (revertibleChanges.length === 0) {
        toast({ title: resolveNonRevertibleToast(fileChanges), variant: 'default' });
        return;
      }
      setChanges(fileChanges);
      setDiffs(fileDiffs);
      setPopoverOpen(true);
    } finally {
      setTriggerLoading(false);
    }
  }, [fetchChanges, fetchDiffs, resolveNonRevertibleToast, t, triggerLoading]);

  const handleConfirmRevert = useCallback(async () => {
    setStatus('loading');
    try {
      const res = await fetch('/api/v1/files/revert/message', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders(),
        },
        body: JSON.stringify({ session_id: chatId, message_id: messageId }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.success) {
          setStatus('success');
          window.dispatchEvent(new CustomEvent('app_resync_required'));
          toast({ title: t('revertMessageSuccess'), variant: 'default' });
        } else {
          setStatus('error');
        }
      } else {
        setStatus('error');
      }
    } catch {
      setStatus('error');
    }
    setTimeout(resetState, 2000);
  }, [chatId, messageId, resetState, t]);

  if (status === 'success') {
    return (
      <span className="p-2 text-green-600 dark:text-green-400">
        <Check size={18} />
      </span>
    );
  }

  if (status === 'error') {
    return (
      <span className="p-2 text-red-500">
        <AlertCircle size={18} />
      </span>
    );
  }

  return (
    <Popover
      open={popoverOpen}
      onOpenChange={(open) => {
        if (open && !changes) {
          return;
        }
        setPopoverOpen(open);
        if (!open) {
          setChanges(null);
          setDiffs(null);
          setExpandedPaths(new Set());
        }
      }}
    >
      <PopoverTrigger asChild>
        <button
          type="button"
          onClick={(event) => {
            event.preventDefault();
            void handleTriggerClick();
          }}
          disabled={status === 'loading' || triggerLoading}
          title={t('revertFiles')}
          className={cn(
            'p-2 rounded-xl transition duration-200',
            popoverOpen
              ? 'text-orange-600 dark:text-orange-400 bg-orange-100 dark:bg-orange-900/30 hover:bg-orange-200 dark:hover:bg-orange-900/50'
              : 'text-black/70 dark:text-white/70 hover:bg-secondary dark:hover:bg-secondary hover:text-black dark:hover:text-white',
            triggerLoading && 'opacity-60 cursor-wait',
          )}
        >
          <Undo2 size={18} className={triggerLoading ? 'animate-spin' : undefined} />
        </button>
      </PopoverTrigger>
      <PopoverContent
        side="bottom"
        align="end"
        className="w-[min(100vw-2rem,28rem)] p-0 overflow-hidden"
      >
        {changes ? (
          <div className="text-sm p-3 max-h-[min(70vh,420px)] overflow-y-auto">
            <p className="font-medium mb-2">{t('revertConfirm')}</p>
            {changes.some((c) => c.revertible === false) && (
              <p className="mb-2 text-xs text-amber-700 dark:text-amber-300/90 leading-relaxed">
                {t('revertPartialSkipHint')}
              </p>
            )}
            <ul className="space-y-2">
              {changes.map((c) => {
                const diffItem = diffs?.find((d) => d.path === c.path);
                const unified = diffItem ? buildUnifiedDiff(diffItem) : null;
                const expanded = expandedPaths.has(c.path);
                const notRevertible = c.revertible === false;
                return (
                  <li
                    key={c.path}
                    className={cn(
                      'rounded-md border border-border/50 bg-muted/20 px-2 py-1.5',
                      notRevertible && 'opacity-70',
                    )}
                  >
                    <button
                      type="button"
                      className={cn(
                        'flex w-full items-center gap-1.5 text-left text-xs',
                        unified ? 'cursor-pointer' : 'cursor-default',
                      )}
                      onClick={unified ? () => toggleExpanded(c.path) : undefined}
                    >
                      {unified ? (
                        expanded ? (
                          <ChevronDown className="w-3 h-3 shrink-0" />
                        ) : (
                          <ChevronRight className="w-3 h-3 shrink-0" />
                        )
                      ) : null}
                      {c.operation === 'create' ? (
                        <IconTrash className="w-3 h-3 shrink-0" />
                      ) : (
                        <IconUndo className="w-3 h-3 shrink-0" />
                      )}
                      <span className="truncate font-mono">{c.path.split('/').pop()}</span>
                      {notRevertible && (
                        <span className="ml-auto text-[10px] text-amber-600 dark:text-amber-400">
                          {c.skip_reason === 'file_too_large'
                            ? t('revertSkipLabelFileTooLarge')
                            : c.skip_reason === 'store_full'
                              ? t('revertSkipLabelStoreFull')
                              : t('revertSkipLabelGeneric')}
                        </span>
                      )}
                      {unified && !expanded && !notRevertible && (
                        <span className="ml-auto text-[10px] text-muted-foreground">{t('revertViewDiff')}</span>
                      )}
                    </button>
                    {unified && expanded && (
                      <div className="mt-1.5 max-w-full overflow-hidden">
                        <DiffViewer diff={unified} filePath={c.path} className="text-[10px]" />
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
            <Button
              type="button"
              size="sm"
              variant="destructive"
              className="mt-3 w-full"
              disabled={status === 'loading'}
              onClick={handleConfirmRevert}
            >
              {t('revertConfirmAction')}
            </Button>
          </div>
        ) : null}
      </PopoverContent>
    </Popover>
  );
};

export default RevertFiles;
