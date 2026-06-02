'use client';

/**
 * Workspace file browser component for Web/SaaS environments
 *
 * [INPUT]
 * - workspacePath: Workspace root directory path
 * - files: File tree entries from useWorkspaceFiles
 * - onFileClick: Callback when a file is clicked for preview
 *
 * [OUTPUT]
 * - WorkspaceFileBrowser: File tree browser with expand/collapse, icons, sizes,
 *   upload (button + drag-and-drop), new directory, inline rename, move,
 *   delete with confirmation, and right-click context menu.
 *
 * [POS]
 * Main Agent's workspace file browser. Displays the workspace directory tree
 * in the sidebar, allowing users to browse, preview, and manage files. Works in
 * Web/SaaS mode via HTTP API (unlike CLIWorkspaceTree which requires Tauri).
 * Write-operation UI primitives are in WorkspaceFileOps.tsx.
 */

import React, { memo, useState, useCallback } from 'react';
import { motion, AnimatePresence, type Variants } from 'framer-motion';
import { ChevronRight, RefreshCw, FolderOpen, AlertTriangle } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { CLIFileIcon } from '@/components/ui/cli-visualization/CLIFileIcon';
import type { FileEntry } from '@/services/chat';
import useChatStore from '@/store/useChatStore';
import {
  ContextMenu,
  UploadDropZone,
  UploadButton,
  NewDirButton,
  InlineRenameInput,
  DeleteConfirmDialog,
  MoveDialog,
  useWorkspaceFileOps,
} from './WorkspaceFileOps';

const containerVariants: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.02, delayChildren: 0.01 } },
  exit: { opacity: 0, transition: { staggerChildren: 0.01, staggerDirection: -1 } },
};

const itemVariants: Variants = {
  hidden: { opacity: 0, x: -8 },
  visible: { opacity: 1, x: 0, transition: { duration: 0.12, ease: 'easeOut' } },
  exit: { opacity: 0, x: -8, transition: { duration: 0.08, ease: 'easeIn' } },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatFileSize(bytes: number | null): string {
  if (bytes === null || bytes === undefined) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ---------------------------------------------------------------------------
// Tree item
// ---------------------------------------------------------------------------

interface TreeItemProps {
  node: FileEntry;
  depth: number;
  expandedPaths: Set<string>;
  onToggle: (path: string) => void;
  onFileClick?: (file: FileEntry) => void;
  onMention?: (file: FileEntry) => void;
  onContextMenu?: (e: React.MouseEvent, node: FileEntry) => void;
  renamingPath: string | null;
  workspace: string;
  onRenameComplete: () => void;
  onRenameCancel: () => void;
}

const TreeItem: React.FC<TreeItemProps> = memo(
  ({
    node,
    depth,
    expandedPaths,
    onToggle,
    onFileClick,
    onMention,
    onContextMenu,
    renamingPath,
    workspace,
    onRenameComplete,
    onRenameCancel,
  }) => {
    const isDir = node.type === 'directory';
    const isExpanded = expandedPaths.has(node.path);
    const hasChildren = isDir && node.children && node.children.length > 0;
    const isRenaming = renamingPath === node.path;

    const handleClick = useCallback(() => {
      if (isDir) {
        onToggle(node.path);
      } else {
        onFileClick?.(node);
      }
    }, [isDir, node, onToggle, onFileClick]);

    return (
      <motion.div variants={itemVariants}>
        <button
          className={cn(
            'flex w-full items-center gap-1 py-1 px-2 rounded text-left',
            'hover:bg-muted/50 transition-colors group text-sm',
          )}
          style={{ paddingLeft: `${depth * 16 + 8}px` }}
          onClick={handleClick}
          onContextMenu={(e) => onContextMenu?.(e, node)}
        >
          <div className="w-4 h-4 flex items-center justify-center shrink-0">
            {hasChildren && (
              <ChevronRight
                className={cn('h-3 w-3 text-muted-foreground transition-transform', isExpanded && 'rotate-90')}
              />
            )}
          </div>

          <CLIFileIcon filename={node.name} isDirectory={isDir} isExpanded={isExpanded} />

          {isRenaming ? (
            <InlineRenameInput
              workspace={workspace}
              node={node}
              onComplete={onRenameComplete}
              onCancel={onRenameCancel}
            />
          ) : (
            <span className="truncate flex-1" title={node.name}>
              {node.name}
            </span>
          )}

          {!isRenaming && !isDir && node.size !== null && (
            <span className="text-xs text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
              {formatFileSize(node.size)}
            </span>
          )}

          {!isRenaming && !isDir && onMention && (
            <span
              role="button"
              tabIndex={-1}
              className="text-xs font-semibold text-primary opacity-0 group-hover:opacity-100 transition-opacity shrink-0 hover:underline cursor-pointer ml-1"
              title="@ mention"
              onClick={(e) => {
                e.stopPropagation();
                onMention(node);
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.stopPropagation();
                  onMention(node);
                }
              }}
            >
              @
            </span>
          )}
        </button>

        <AnimatePresence>
          {isExpanded && hasChildren && (
            <motion.div
              variants={containerVariants}
              initial="hidden"
              animate="visible"
              exit="exit"
              className="relative"
            >
              <div
                className="absolute left-0 top-0 bottom-0 border-l border-border/40"
                style={{ marginLeft: `${depth * 16 + 16}px` }}
              />
              {node.children!.map((child) => (
                <TreeItem
                  key={child.path}
                  node={child}
                  depth={depth + 1}
                  expandedPaths={expandedPaths}
                  onToggle={onToggle}
                  onFileClick={onFileClick}
                  onMention={onMention}
                  onContextMenu={onContextMenu}
                  renamingPath={renamingPath}
                  workspace={workspace}
                  onRenameComplete={onRenameComplete}
                  onRenameCancel={onRenameCancel}
                />
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    );
  },
);
TreeItem.displayName = 'TreeItem';

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export interface WorkspaceFileBrowserProps {
  workspacePath: string;
  files: FileEntry[];
  loading?: boolean;
  error?: string | null;
  truncated?: boolean;
  onRefresh?: () => void;
  onFileClick?: (file: FileEntry) => void;
  className?: string;
}

export const WorkspaceFileBrowser: React.FC<WorkspaceFileBrowserProps> = memo(
  ({ workspacePath, files, loading = false, error = null, truncated = false, onRefresh, onFileClick, className }) => {
    const t = useTranslations('workspace');
    const [expandedPaths, setExpandedPaths] = useState<Set<string>>(new Set());

    const ops = useWorkspaceFileOps(workspacePath, onRefresh ?? (() => {}));

    const handleToggle = useCallback((path: string) => {
      setExpandedPaths((prev) => {
        const next = new Set(prev);
        if (next.has(path)) next.delete(path);
        else next.add(path);
        return next;
      });
    }, []);

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

    const workspaceName = workspacePath.split('/').pop() || workspacePath;

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
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <RefreshCw className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center py-8 px-4 text-muted-foreground">
              <AlertTriangle className="h-6 w-6 mb-2 text-destructive" />
              <span className="text-sm text-center">{error}</span>
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
                  <TreeItem
                    key={node.path}
                    node={node}
                    depth={0}
                    expandedPaths={expandedPaths}
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
            />
          )}
        </AnimatePresence>

        <AnimatePresence>
          {ops.deletingNode && (
            <DeleteConfirmDialog
              node={ops.deletingNode}
              onConfirm={() => ops.handleDelete(ops.deletingNode!)}
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
