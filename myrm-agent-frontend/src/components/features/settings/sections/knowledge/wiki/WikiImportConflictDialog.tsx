'use client';

import { useState } from 'react';
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
} from '@/components/primitives/alert-dialog';
import { Textarea } from '@/components/primitives/textarea';

interface WikiImportConflictDialogProps {
  open: boolean;
  conflictPaths: string[];
  onClose: () => void;
  onKeepSkipped: () => void;
  onSupersede: (reason: string) => void;
}

export function WikiImportConflictDialog({
  open,
  conflictPaths,
  onClose,
  onKeepSkipped,
  onSupersede,
}: WikiImportConflictDialogProps) {
  const t = useTranslations('settings.wiki.import');
  const [reason, setReason] = useState('');

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen) {
      setReason('');
      onClose();
    }
  };

  const previewPaths = conflictPaths.slice(0, 8);
  const remaining = conflictPaths.length - previewPaths.length;

  return (
    <AlertDialog open={open} onOpenChange={handleOpenChange}>
      <AlertDialogContent className="w-[calc(100vw-2rem)] max-w-[520px] sm:max-w-[520px]">
        <AlertDialogHeader>
          <AlertDialogTitle>{t('conflictTitle')}</AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div className="space-y-3 text-sm text-muted-foreground">
              <p>{t('conflictDescription', { count: conflictPaths.length })}</p>
              <ul className="max-h-40 list-disc space-y-1 overflow-y-auto pl-5 font-mono text-xs text-foreground/80">
                {previewPaths.map((path) => (
                  <li key={path}>{path}</li>
                ))}
              </ul>
              {remaining > 0 ? <p className="text-xs">{t('conflictMore', { count: remaining })}</p> : null}
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>

        <div className="space-y-2">
          <label htmlFor="wiki-import-supersede-reason" className="text-sm font-medium text-foreground">
            {t('supersedeReasonLabel')}
          </label>
          <Textarea
            id="wiki-import-supersede-reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder={t('supersedeReasonPlaceholder')}
            rows={3}
          />
        </div>

        <AlertDialogFooter className="flex-col gap-2 sm:flex-row">
          <AlertDialogCancel onClick={onKeepSkipped}>{t('conflictKeepSkipped')}</AlertDialogCancel>
          <AlertDialogAction
            disabled={!reason.trim()}
            onClick={() => {
              const trimmed = reason.trim();
              setReason('');
              onSupersede(trimmed);
            }}
          >
            {t('conflictSupersede')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
