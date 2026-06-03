'use client';

/**
 * Workspace file write-operation UI primitives
 *
 * [INPUT]
 * - @/services/chat workspace ops API functions
 * - FileEntry from @/services/chat
 *
 * [OUTPUT]
 * - ContextMenu: right-click menu with viewport boundary detection
 * - UploadDropZone: drag-and-drop overlay + hidden file input
 * - UploadButton: click-to-browse file upload button
 * - NewDirButton: inline new-directory creation
 * - InlineRenameInput: inline name editing field
 * - UploadProgressBar: upload progress indicator
 * - useWorkspaceFileOps: hook for workspace file operation state
 * - Re-exports: DeleteConfirmDialog, MoveDialog from WorkspaceDialogs
 *
 * [POS]
 * Write-operation UI primitives for WorkspaceFileBrowser.
 * Dialogs extracted to WorkspaceDialogs.tsx to stay under 400 lines.
 */

import React, { useRef, useState, useCallback, useEffect, type DragEvent, type KeyboardEvent } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Upload, FolderPlus, Pencil, Move, Trash2 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { cn } from '@/lib/utils/classnameUtils';
import type { FileEntry } from '@/services/chat';
import { uploadToWorkspace, mkdirInWorkspace, renameInWorkspace, deleteInWorkspace } from '@/services/chat';

export { DeleteConfirmDialog } from './WorkspaceDialogs';
export { MoveDialog } from './WorkspaceDialogs';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ContextMenuState {
  x: number;
  y: number;
  node: FileEntry;
}

interface ContextMenuProps {
  state: ContextMenuState;
  onClose: () => void;
  onRename: (node: FileEntry) => void;
  onDelete: (node: FileEntry) => void;
  onMove: (node: FileEntry) => void;
}

// ---------------------------------------------------------------------------
// Context menu
// ---------------------------------------------------------------------------

export const ContextMenu: React.FC<ContextMenuProps> = ({ state, onClose, onRename, onDelete, onMove }) => {
  const t = useTranslations('workspace');
  const menuRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ x: state.x, y: state.y });

  useEffect(() => {
    const handler = () => onClose();
    window.addEventListener('click', handler);
    window.addEventListener('contextmenu', handler);
    return () => {
      window.removeEventListener('click', handler);
      window.removeEventListener('contextmenu', handler);
    };
  }, [onClose]);

  useEffect(() => {
    const el = menuRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    setPos({
      x: rect.right > vw ? Math.max(0, state.x - rect.width) : state.x,
      y: rect.bottom > vh ? Math.max(0, state.y - rect.height) : state.y,
    });
  }, [state.x, state.y]);

  const items = [
    { icon: Pencil, label: t('rename'), action: () => onRename(state.node) },
    { icon: Move, label: t('move'), action: () => onMove(state.node) },
    { icon: Trash2, label: t('delete'), action: () => onDelete(state.node), danger: true },
  ];

  return (
    <motion.div
      ref={menuRef}
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ duration: 0.1 }}
      className="fixed z-50 bg-popover border border-border rounded-lg shadow-lg py-1 min-w-[160px]"
      style={{ left: pos.x, top: pos.y }}
      onClick={(e) => e.stopPropagation()}
    >
      {items.map(({ icon: Icon, label, action, danger }) => (
        <button
          key={label}
          className={cn(
            'flex items-center gap-2 w-full px-3 py-1.5 text-sm hover:bg-muted transition-colors',
            danger && 'text-destructive hover:text-destructive',
          )}
          onClick={(e) => {
            e.stopPropagation();
            action();
            onClose();
          }}
        >
          <Icon className="h-3.5 w-3.5" />
          {label}
        </button>
      ))}
    </motion.div>
  );
};

// ---------------------------------------------------------------------------
// Upload drop zone
// ---------------------------------------------------------------------------

interface UploadDropZoneProps {
  workspace: string;
  targetDir: string;
  onComplete: () => void;
  children: React.ReactNode;
  className?: string;
}

export const UploadDropZone: React.FC<UploadDropZoneProps> = ({
  workspace,
  targetDir,
  onComplete,
  children,
  className,
}) => {
  const t = useTranslations('workspace');
  const [dragging, setDragging] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const dragCounter = useRef(0);

  const handleDragEnter = useCallback((e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current++;
    if (e.dataTransfer.types.includes('Files')) setDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current--;
    if (dragCounter.current === 0) setDragging(false);
  }, []);

  const handleDragOver = useCallback((e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const handleDrop = useCallback(
    async (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setDragging(false);
      dragCounter.current = 0;

      const fileList = Array.from(e.dataTransfer.files);
      if (fileList.length === 0) return;

      setProgress(0);
      try {
        const result = await uploadToWorkspace(workspace, fileList, targetDir, setProgress);
        toast.success(t('uploadSuccess', { count: result.uploaded_count }));
        onComplete();
      } catch (err) {
        toast.error(err instanceof Error ? err.message : t('uploadFailed'));
      } finally {
        setProgress(null);
      }
    },
    [workspace, targetDir, onComplete, t],
  );

  return (
    <div
      className={cn('relative', className)}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      {children}

      <AnimatePresence>
        {dragging && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 z-40 flex items-center justify-center bg-primary/10 border-2 border-dashed border-primary rounded-lg backdrop-blur-sm"
          >
            <div className="flex flex-col items-center gap-2 text-primary">
              <Upload className="h-8 w-8" />
              <span className="text-sm font-medium">{t('dropToUpload')}</span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {progress !== null && <UploadProgressBar percent={progress} />}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Upload button (click-to-browse)
// ---------------------------------------------------------------------------

interface UploadButtonProps {
  workspace: string;
  targetDir: string;
  onComplete: () => void;
}

export const UploadButton: React.FC<UploadButtonProps> = ({ workspace, targetDir, onComplete }) => {
  const t = useTranslations('workspace');
  const inputRef = useRef<HTMLInputElement>(null);
  const [progress, setProgress] = useState<number | null>(null);

  const handleFiles = useCallback(
    async (fileList: FileList | null) => {
      if (!fileList || fileList.length === 0) return;
      const files = Array.from(fileList);

      setProgress(0);
      try {
        const result = await uploadToWorkspace(workspace, files, targetDir, setProgress);
        toast.success(t('uploadSuccess', { count: result.uploaded_count }));
        onComplete();
      } catch (err) {
        toast.error(err instanceof Error ? err.message : t('uploadFailed'));
      } finally {
        setProgress(null);
        if (inputRef.current) inputRef.current.value = '';
      }
    },
    [workspace, targetDir, onComplete, t],
  );

  return (
    <>
      <button
        onClick={() => inputRef.current?.click()}
        className="p-1 rounded hover:bg-muted transition-colors"
        title={t('upload')}
        disabled={progress !== null}
      >
        <Upload className="h-4 w-4 text-muted-foreground" />
      </button>
      <input ref={inputRef} type="file" multiple className="hidden" onChange={(e) => handleFiles(e.target.files)} />
      {progress !== null && <UploadProgressBar percent={progress} />}
    </>
  );
};

// ---------------------------------------------------------------------------
// New-directory button
// ---------------------------------------------------------------------------

interface NewDirButtonProps {
  workspace: string;
  currentDir: string;
  onComplete: () => void;
}

export const NewDirButton: React.FC<NewDirButtonProps> = ({ workspace, currentDir, onComplete }) => {
  const t = useTranslations('workspace');
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState('');

  const handleSubmit = useCallback(async () => {
    const trimmed = name.trim();
    if (!trimmed) {
      setEditing(false);
      return;
    }
    try {
      await mkdirInWorkspace(workspace, `${currentDir}/${trimmed}`);
      toast.success(t('mkdirSuccess', { name: trimmed }));
      onComplete();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t('mkdirFailed'));
    }
    setEditing(false);
    setName('');
  }, [workspace, currentDir, name, onComplete, t]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Enter') handleSubmit();
      else if (e.key === 'Escape') {
        setEditing(false);
        setName('');
      }
    },
    [handleSubmit],
  );

  if (editing) {
    return (
      <div className="flex items-center gap-1 px-2">
        <FolderPlus className="h-3.5 w-3.5 text-amber-500 shrink-0" />
        <input
          autoFocus
          value={name}
          onChange={(e) => setName(e.target.value)}
          onBlur={handleSubmit}
          onKeyDown={handleKeyDown}
          className="flex-1 text-sm bg-transparent border-b border-primary outline-none px-1 py-0.5"
          placeholder={t('newDirPlaceholder')}
        />
      </div>
    );
  }

  return (
    <button
      onClick={() => setEditing(true)}
      className="p-1 rounded hover:bg-muted transition-colors"
      title={t('newDir')}
    >
      <FolderPlus className="h-4 w-4 text-muted-foreground" />
    </button>
  );
};

// ---------------------------------------------------------------------------
// Inline rename input
// ---------------------------------------------------------------------------

interface InlineRenameInputProps {
  workspace: string;
  node: FileEntry;
  onComplete: () => void;
  onCancel: () => void;
}

export const InlineRenameInput: React.FC<InlineRenameInputProps> = ({ workspace, node, onComplete, onCancel }) => {
  const t = useTranslations('workspace');
  const [value, setValue] = useState(node.name);

  const handleSubmit = useCallback(async () => {
    const trimmed = value.trim();
    if (!trimmed || trimmed === node.name) {
      onCancel();
      return;
    }
    try {
      await renameInWorkspace(workspace, node.path, trimmed);
      toast.success(t('renameSuccess'));
      onComplete();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t('renameFailed'));
      onCancel();
    }
  }, [workspace, node, value, onComplete, onCancel, t]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Enter') handleSubmit();
      else if (e.key === 'Escape') onCancel();
    },
    [handleSubmit, onCancel],
  );

  return (
    <input
      autoFocus
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onBlur={handleSubmit}
      onKeyDown={handleKeyDown}
      onClick={(e) => e.stopPropagation()}
      className="flex-1 text-sm bg-transparent border border-primary rounded px-1 py-0.5 outline-none min-w-0"
    />
  );
};

// ---------------------------------------------------------------------------
// Upload progress bar
// ---------------------------------------------------------------------------

const UploadProgressBar: React.FC<{ percent: number }> = ({ percent }) => {
  const t = useTranslations('workspace');

  return (
    <div className="absolute bottom-0 left-0 right-0 px-3 py-1.5 bg-background/80 backdrop-blur-sm border-t border-border">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Upload className="h-3 w-3" />
        <span>{t('uploading', { percent })}</span>
      </div>
      <div className="mt-1 h-1 bg-muted rounded-full overflow-hidden">
        <motion.div
          className="h-full bg-primary rounded-full"
          initial={{ width: 0 }}
          animate={{ width: `${percent}%` }}
          transition={{ duration: 0.15 }}
        />
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Hook: workspace file operations
// ---------------------------------------------------------------------------

export function useWorkspaceFileOps(workspace: string, onRefresh: () => void) {
  const t = useTranslations('workspace');
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);
  const [renamingPath, setRenamingPath] = useState<string | null>(null);
  const [deletingNode, setDeletingNode] = useState<FileEntry | null>(null);
  const [movingNode, setMovingNode] = useState<FileEntry | null>(null);

  const handleContextMenu = useCallback((e: React.MouseEvent, node: FileEntry) => {
    e.preventDefault();
    e.stopPropagation();
    setContextMenu({ x: e.clientX, y: e.clientY, node });
  }, []);

  const handleDelete = useCallback(
    async (node: FileEntry) => {
      try {
        await deleteInWorkspace(workspace, node.path);
        toast.success(t('deleteSuccess', { name: node.name }));
        onRefresh();
      } catch (err) {
        toast.error(err instanceof Error ? err.message : t('deleteFailed'));
      }
      setDeletingNode(null);
    },
    [workspace, onRefresh, t],
  );

  return {
    contextMenu,
    setContextMenu,
    renamingPath,
    setRenamingPath,
    deletingNode,
    setDeletingNode,
    movingNode,
    setMovingNode,
    handleContextMenu,
    handleDelete,
  };
}
