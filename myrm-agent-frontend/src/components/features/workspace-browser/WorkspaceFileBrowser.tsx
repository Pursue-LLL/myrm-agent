'use client';

/**
 * Workspace file browser component for Web/SaaS environments
 *
 * [INPUT]
 * - workspacePath: Workspace root directory path
 * - files: File tree entries from useWorkspaceFiles
 * - loading / error: Scan state from useWorkspaceFiles; a refresh leaves the tree on screen, a failed scan shows
 *   a localized message instead of the server's text
 * - onFileClick: Callback when a file is clicked for preview
 * - onLoadChildren: Loads a folder the initial scan did not reach (`children: null`) when it is opened
 *
 * [OUTPUT]
 * - WorkspaceFileBrowser: File tree browser with expand/collapse (folders below the scanned depth load on
 *   open), icons, sizes, upload (button + drag-and-drop), new directory, inline rename, move,
 *   delete with confirmation, and right-click context menu. The header names the chat's own workspace
 *   in the user's language rather than by its folder id.
 *
 * [POS]
 * Main Agent's workspace file browser. Displays the workspace directory tree
 * in the sidebar, allowing users to browse, preview, and manage files. Works in
 * Web/SaaS mode via HTTP API.
 * Tree rows are in WorkspaceFileTree.tsx, the right-click menu in WorkspaceContextMenu.tsx, other write-operation
 * UI primitives in WorkspaceFileOps.tsx.
 */

import React, { memo, useState, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { RefreshCw, FolderOpen, AlertTriangle } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { cn } from '@/lib/utils/classnameUtils';
import type { FileEntry } from '@/services/chat';
import useChatStore from '@/store/useChatStore';
import {
  UploadDropZone,
  UploadButton,
  NewDirButton,
  DeleteConfirmDialog,
  MoveDialog,
  useWorkspaceFileOps,
} from './WorkspaceFileOps';
import { ContextMenu } from './WorkspaceContextMenu';
import { WorkspaceFileTreeItem, containerVariants } from './WorkspaceFileTree';

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export interface WorkspaceFileBrowserProps {
  workspacePath: string;
  files: FileEntry[];
  /** A scan is running. The tree stays on screen meanwhile; only an empty browser is replaced by a spinner. */
  loading?: boolean;
  /** The scan failed. The browser words the failure itself: this text comes from the server and is never shown. */
  error?: string | null;
  truncated?: boolean;
  onRefresh?: () => void;
  onFileClick?: (file: FileEntry) => void;
  /** Loads the contents of a folder the initial scan did not reach; rejects when the folder cannot be read. */
  onLoadChildren: (dirPath: string) => Promise<void>;
  className?: string;
}

export const WorkspaceFileBrowser: React.FC<WorkspaceFileBrowserProps> = memo(
  ({
    workspacePath,
    files,
    loading = false,
    error = null,
    truncated = false,
    onRefresh,
    onFileClick,
    onLoadChildren,
    className,
  }) => {
    const t = useTranslations('workspace');
    const chatId = useChatStore((s) => s.chatId);
    const [expandedPaths, setExpandedPaths] = useState<Set<string>>(new Set());
    const [loadingPaths, setLoadingPaths] = useState<ReadonlySet<string>>(new Set());
    const loadingRef = useRef<Set<string>>(new Set());

    const ops = useWorkspaceFileOps(workspacePath, onRefresh ?? (() => {}));
    const deletingNode = ops.deletingNode;

    const loadFolder = useCallback(
      async (dirPath: string) => {
        if (loadingRef.current.has(dirPath)) {
          return;
        }
        loadingRef.current.add(dirPath);
        setLoadingPaths(new Set(loadingRef.current));
        try {
          await onLoadChildren(dirPath);
        } catch {
          toast.error(t('folderLoadFailed'));
          setExpandedPaths((prev) => {
            const next = new Set(prev);
            next.delete(dirPath);
            return next;
          });
        } finally {
          loadingRef.current.delete(dirPath);
          setLoadingPaths(new Set(loadingRef.current));
        }
      },
      [onLoadChildren, t],
    );

    const handleToggle = useCallback(
      (node: FileEntry) => {
        setExpandedPaths((prev) => {
          const next = new Set(prev);
          if (next.has(node.path)) {
            next.delete(node.path);
          } else {
            next.add(node.path);
          }
          return next;
        });
        if (node.type === 'directory' && node.children == null) {
          void loadFolder(node.path);
        }
      },
      [loadFolder],
    );

    const handleOrganize = useCallback(
      (file: FileEntry) => {
        const relativePath = file.path.startsWith(workspacePath)
          ? file.path.slice(workspacePath.length).replace(/^\//, '') || '.'
          : file.name;
        useChatStore.getState().setInputMessage(t('organizePrompt', { path: relativePath }));
        toast.success(t('organizeFolder'));
      },
      [workspacePath, t],
    );

    const handleSetProjectRoot = useCallback(
      (file: FileEntry) => {
        const relativePath = file.path.startsWith(workspacePath)
          ? file.path.slice(workspacePath.length).replace(/^\//, '') || '.'
          : file.name;
        useChatStore.getState().setInputMessage(t('scopedPrompt', { path: relativePath }));
        toast.success(t('projectRootSet', { path: relativePath }));
      },
      [workspacePath, t],
    );

    const handleMention = useCallback(
      (file: FileEntry) => {
        const relativePath = file.path.startsWith(workspacePath)
          ? file.path.slice(workspacePath.length).replace(/^\//, '')
          : file.name;
        useChatStore.getState().addMentionReference({
          type: file.type === 'directory' ? 'workspace_folder' : 'workspace_file',
          label: `@${file.name}`,
          path: relativePath,
          source: 'workspace',
          size: file.size,
        });
      },
      [workspacePath],
    );

    const handleRenameComplete = useCallback(() => {
      ops.setRenamingPath(null);
      onRefresh?.();
    }, [ops, onRefresh]);

    const handleRenameCancel = useCallback(() => {
      ops.setRenamingPath(null);
    }, [ops]);

    // The chat's own workspace is a folder named after the chat id; that name means nothing to the user.
    const folderName =
      workspacePath
        .split(/[\\/]+/)
        .filter(Boolean)
        .pop() ?? workspacePath;
    const workspaceName = chatId && folderName === `chat_${chatId}` ? t('sessionWorkspace') : folderName;

    return (
      <UploadDropZone
        workspace={workspacePath}
        targetDir=""
        onComplete={onRefresh ?? (() => {})}
        className={cn('flex flex-col h-full', className)}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-3 py-2 border-b border-border">
          <div className="flex items-center gap-2 min-w-0">
            <FolderOpen className="h-4 w-4 text-amber-500 shrink-0" />
            <span className="text-sm font-medium truncate" title={workspacePath}>
              {workspaceName}
            </span>
          </div>
          <div className="flex items-center gap-0.5 shrink-0">
            <UploadButton workspace={workspacePath} targetDir="" onComplete={onRefresh ?? (() => {})} />
            <NewDirButton workspace={workspacePath} currentDir={workspacePath} onComplete={onRefresh ?? (() => {})} />
            {onRefresh && (
              <button
                onClick={onRefresh}
                disabled={loading}
                className={cn('p-1 rounded hover:bg-muted transition-colors', loading && 'animate-spin')}
                title={t('refresh')}
              >
                <RefreshCw className="h-4 w-4 text-muted-foreground" />
              </button>
            )}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto py-1">
          {loading && files.length === 0 ? (
            <div className="flex items-center justify-center py-8">
              <RefreshCw className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center py-8 px-4 text-muted-foreground">
              <AlertTriangle className="h-6 w-6 mb-2 text-destructive" />
              <span className="text-sm text-center">{t('folderLoadFailed')}</span>
            </div>
          ) : files.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
              <FolderOpen className="h-8 w-8 mb-2" />
              <span className="text-sm">{t('emptyDir')}</span>
            </div>
          ) : (
            <>
              <motion.div variants={containerVariants} initial="hidden" animate="visible">
                {files.map((node) => (
                  <WorkspaceFileTreeItem
                    key={node.path}
                    node={node}
                    depth={0}
                    expandedPaths={expandedPaths}
                    loadingPaths={loadingPaths}
                    onToggle={handleToggle}
                    onFileClick={onFileClick}
                    onMention={handleMention}
                    onContextMenu={ops.handleContextMenu}
                    renamingPath={ops.renamingPath}
                    workspace={workspacePath}
                    onRenameComplete={handleRenameComplete}
                    onRenameCancel={handleRenameCancel}
                  />
                ))}
              </motion.div>
              {truncated && <div className="px-3 py-2 text-xs text-muted-foreground text-center">{t('truncated')}</div>}
            </>
          )}
        </div>

        {/* Overlays */}
        <AnimatePresence>
          {ops.contextMenu && (
            <ContextMenu
              state={ops.contextMenu}
              onClose={() => ops.setContextMenu(null)}
              onRename={(node) => ops.setRenamingPath(node.path)}
              onDelete={(node) => ops.setDeletingNode(node)}
              onMove={(node) => ops.setMovingNode(node)}
              onOrganize={handleOrganize}
              onSetProjectRoot={handleSetProjectRoot}
            />
          )}
        </AnimatePresence>

        <AnimatePresence>
          {deletingNode && (
            <DeleteConfirmDialog
              node={deletingNode}
              onConfirm={() => ops.handleDelete(deletingNode)}
              onCancel={() => ops.setDeletingNode(null)}
            />
          )}
        </AnimatePresence>

        <AnimatePresence>
          {ops.movingNode && (
            <MoveDialog
              node={ops.movingNode}
              workspace={workspacePath}
              onComplete={() => {
                ops.setMovingNode(null);
                onRefresh?.();
              }}
              onCancel={() => ops.setMovingNode(null)}
            />
          )}
        </AnimatePresence>
      </UploadDropZone>
    );
  },
);

WorkspaceFileBrowser.displayName = 'WorkspaceFileBrowser';
