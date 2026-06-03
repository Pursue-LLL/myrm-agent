'use client';

import { Undo2, Check, AlertCircle } from 'lucide-react';
import { useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';
import { IconTrash, IconUndo } from '@/components/features/icons/PremiumIcons';

interface FileChange {
  path: string;
  operation: string;
  has_original: boolean;
  timestamp: number;
}

interface RevertFilesProps {
  chatId: string;
  messageId: string;
}

const RevertFiles = ({ chatId, messageId }: RevertFilesProps) => {
  const t = useTranslations('messageActions');
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [changes, setChanges] = useState<FileChange[] | null>(null);
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
      }, 2000);
      return;
    }

    const fileChanges = await fetchChanges();
    if (!fileChanges) return;
    setChanges(fileChanges);
    setShowConfirm(true);
  }, [showConfirm, fetchChanges, chatId, messageId]);

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
            className={`p-2 rounded-xl transition duration-200 ${
              showConfirm
                ? 'text-orange-600 dark:text-orange-400 bg-orange-100 dark:bg-orange-900/30 hover:bg-orange-200 dark:hover:bg-orange-900/50'
                : 'text-black/70 dark:text-white/70 hover:bg-secondary dark:hover:bg-secondary hover:text-black dark:hover:text-white'
            }`}
          >
            <Undo2 size={18} />
          </button>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="max-w-xs">
          {showConfirm && changes ? (
            <div className="text-sm">
              <p className="font-medium mb-1">{t('revertConfirm')}</p>
              <ul className="space-y-0.5">
                {changes.map((c) => (
                  <li key={c.path} className="text-xs opacity-80 truncate">
                    {c.operation === 'create' ? (
                      <IconTrash className="w-3 h-3 inline" />
                    ) : (
                      <IconUndo className="w-3 h-3 inline" />
                    )}{' '}
                    {c.path.split('/').pop()}
                  </li>
                ))}
              </ul>
              <p className="text-xs opacity-60 mt-1">{t('revertClickAgain')}</p>
            </div>
          ) : (
            <p>{t('revertFiles')}</p>
          )}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};

export default RevertFiles;
