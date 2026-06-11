'use client';

import React, { useState, useCallback } from 'react';
import { History, X } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import useChatStore from '@/store/useChatStore';
import FileSnapshotList from './FileSnapshotList';

const FileSnapshotPanel: React.FC = () => {
  const t = useTranslations('fileSnapshot');
  const [isOpen, setIsOpen] = useState(false);
  const workingDir = useChatStore((s) => s.workspaceDir);

  const handleRestoreSuccess = useCallback(() => {
    window.dispatchEvent(new CustomEvent('app_resync_required'));
  }, []);

  if (!workingDir) return null;

  return (
    <>
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        className={cn(
          'fixed bottom-24 right-6 p-3 rounded-full shadow-lg transition-colors z-50',
          'flex items-center justify-center',
          'max-sm:bottom-20 max-sm:right-4',
          isOpen
            ? 'bg-primary text-primary-foreground ring-2 ring-primary/30'
            : 'bg-secondary text-secondary-foreground hover:bg-secondary/90',
        )}
        title={t('panelTitle')}
        aria-label={t('panelTitle')}
      >
        <History size={20} />
      </button>

      {isOpen && (
        <div className="fixed inset-y-0 right-0 z-50 w-full max-w-md bg-background border-l border-border shadow-2xl flex flex-col animate-in slide-in-from-right duration-200">
          <div className="flex items-center justify-between px-4 py-3 border-b border-border">
            <h2 className="text-sm font-semibold">{t('panelTitle')}</h2>
            <button
              onClick={() => setIsOpen(false)}
              className="p-1 rounded hover:bg-muted transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto">
            <FileSnapshotList workingDir={workingDir} onRestoreSuccess={handleRestoreSuccess} />
          </div>
        </div>
      )}
    </>
  );
};

export default React.memo(FileSnapshotPanel);
