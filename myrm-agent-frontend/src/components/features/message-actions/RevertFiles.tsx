'use client';

import { Undo2, Check, AlertCircle, ChevronDown, ChevronRight } from 'lucide-react';
import { useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { createPatch } from 'diff';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';
import { IconTrash, IconUndo } from '@/components/features/icons/PremiumIcons';
import { DiffViewer } from '@/lib/diff/DiffViewer';
import { cn } from '@/lib/utils/classnameUtils';

interface FileChange {
  path: string;
  operation: string;
  has_original: boolean;
  timestamp: number;
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
  const [showConfirm, setShowConfirm] = useState(false);

  const fetchChanges = useCallback(async () => {
    try {
      const res = await fetch(`/api/v1/files/revert/changes/${chatId}/${messageId}`);
      if (!res.ok) return null;
      const data: FileChange[] = await res.json();
      return data.length > 0 ? data : null;
    } catch {
      return null;
    }
  }, [chatId, messageId]);

  const fetchDiffs = useCallback(async () => {
    try {
      const res = await fetch(`/api/v1/files/revert/diff/${chatId}/${messageId}`);
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

  const handleClick = useCallback(async () => {
    if (showConfirm) {
      setStatus('loading');
      try {
        const res = await fetch('/api/v1/files/revert/message', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: chatId, message_id: messageId }),
        });
        if (res.ok) {
          const data = await res.json();
          setStatus(data.success ? 'success' : 'error');
        } else {
          setStatus('error');
        }
      } catch {
        setStatus('error');
      }
      setTimeout(() => {
        setStatus('idle');
        setShowConfirm(false);
        setChanges(null);
        setDiffs(null);
        setExpandedPaths(new Set());
      }, 2000);
      return;
    }

    const [fileChanges, fileDiffs] = await Promise.all([fetchChanges(), fetchDiffs()]);
    if (!fileChanges) return;
    setChanges(fileChanges);
    setDiffs(fileDiffs);
    setShowConfirm(true);
  }, [showConfirm, fetchChanges, fetchDiffs, chatId, messageId]);

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
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            onClick={handleClick}
            disabled={status === 'loading'}
            className={cn(
              'p-2 rounded-xl transition duration-200',
              showConfirm
                ? 'text-orange-600 dark:text-orange-400 bg-orange-100 dark:bg-orange-900/30 hover:bg-orange-200 dark:hover:bg-orange-900/50'
                : 'text-black/70 dark:text-white/70 hover:bg-secondary dark:hover:bg-secondary hover:text-black dark:hover:text-white',
            )}
          >
            <Undo2 size={18} />
          </button>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="max-w-md p-0 overflow-hidden">
          {showConfirm && changes ? (
            <div className="text-sm p-3 max-h-[min(70vh,420px)] overflow-y-auto">
              <p className="font-medium mb-2">{t('revertConfirm')}</p>
              <ul className="space-y-2">
                {changes.map((c) => {
                  const diffItem = diffs?.find((d) => d.path === c.path);
                  const unified = diffItem ? buildUnifiedDiff(diffItem) : null;
                  const expanded = expandedPaths.has(c.path);
                  return (
                    <li key={c.path} className="rounded-md border border-border/50 bg-muted/20 px-2 py-1.5">
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
                        {unified && !expanded && (
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
              <p className="text-xs opacity-60 mt-2">{t('revertClickAgain')}</p>
            </div>
          ) : (
            <p className="p-3">{t('revertFiles')}</p>
          )}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};

export default RevertFiles;
