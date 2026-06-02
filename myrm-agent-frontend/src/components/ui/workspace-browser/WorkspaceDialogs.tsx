'use client';

/**
 * Workspace file operation dialogs
 *
 * [INPUT]
 * - FileEntry from @/services/chat
 * - moveInWorkspace from @/services/chat
 *
 * [OUTPUT]
 * - DeleteConfirmDialog: confirmation modal before file/dir deletion
 * - MoveDialog: modal for specifying move-target directory
 *
 * [POS]
 * Extracted from WorkspaceFileOps.tsx to keep each file under 400 lines.
 */

import React, { useState, useCallback, type KeyboardEvent } from 'react';
import { motion } from 'framer-motion';
import { AlertTriangle } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import type { FileEntry } from '@/services/chat';
import { moveInWorkspace } from '@/services/chat';

// ---------------------------------------------------------------------------
// Delete confirm dialog
// ---------------------------------------------------------------------------

interface DeleteConfirmDialogProps {
  node: FileEntry;
  onConfirm: () => void;
  onCancel: () => void;
}

export const DeleteConfirmDialog: React.FC<DeleteConfirmDialogProps> = ({ node, onConfirm, onCancel }) => {
  const t = useTranslations('workspace');

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onCancel}
    >
      <motion.div
        initial={{ scale: 0.95 }}
        animate={{ scale: 1 }}
        exit={{ scale: 0.95 }}
        className="bg-popover border border-border rounded-xl shadow-xl p-6 max-w-sm mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 rounded-full bg-destructive/10">
            <AlertTriangle className="h-5 w-5 text-destructive" />
          </div>
          <div>
            <h3 className="font-semibold text-sm">{t('deleteConfirmTitle')}</h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              {t('deleteConfirmDesc', {
                name: node.name,
                type: node.type === 'directory' ? t('directory') : t('file'),
              })}
            </p>
          </div>
        </div>
        <div className="flex justify-end gap-2">
          <button onClick={onCancel} className="px-3 py-1.5 text-sm rounded-lg hover:bg-muted transition-colors">
            {t('cancel')}
          </button>
          <button
            onClick={onConfirm}
            className="px-3 py-1.5 text-sm rounded-lg bg-destructive text-destructive-foreground hover:bg-destructive/90 transition-colors"
          >
            {t('confirmDelete')}
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
};

// ---------------------------------------------------------------------------
// Move dialog
// ---------------------------------------------------------------------------

interface MoveDialogProps {
  node: FileEntry;
  workspace: string;
  onComplete: () => void;
  onCancel: () => void;
}

export const MoveDialog: React.FC<MoveDialogProps> = ({ node, workspace, onComplete, onCancel }) => {
  const t = useTranslations('workspace');
  const [targetDir, setTargetDir] = useState('');

  const handleSubmit = useCallback(async () => {
    const trimmed = targetDir.trim();
    if (!trimmed) {
      onCancel();
      return;
    }
    try {
      await moveInWorkspace(workspace, node.path, trimmed);
      toast.success(t('moveSuccess'));
      onComplete();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t('moveFailed'));
    }
  }, [workspace, node, targetDir, onComplete, onCancel, t]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Enter') handleSubmit();
      else if (e.key === 'Escape') onCancel();
    },
    [handleSubmit, onCancel],
  );

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onCancel}
    >
      <motion.div
        initial={{ scale: 0.95 }}
        animate={{ scale: 1 }}
        exit={{ scale: 0.95 }}
        className="bg-popover border border-border rounded-xl shadow-xl p-6 max-w-sm mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="font-semibold text-sm mb-3">{t('moveTitle', { name: node.name })}</h3>
        <input
          autoFocus
          value={targetDir}
          onChange={(e) => setTargetDir(e.target.value)}
          onKeyDown={handleKeyDown}
          className="w-full text-sm bg-input border border-border rounded-lg px-3 py-2 outline-none focus:ring-1 focus:ring-primary"
          placeholder={t('movePlaceholder')}
        />
        <div className="flex justify-end gap-2 mt-4">
          <button onClick={onCancel} className="px-3 py-1.5 text-sm rounded-lg hover:bg-muted transition-colors">
            {t('cancel')}
          </button>
          <button
            onClick={handleSubmit}
            className="px-3 py-1.5 text-sm rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            {t('moveConfirm')}
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
};
