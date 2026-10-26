'use client';

/**
 * Tree rows of the workspace file browser
 *
 * [INPUT]
 * - node: FileEntry of the row; its `children` are rendered recursively when the row is expanded
 * - expandedPaths / loadingPaths: Which folders are open and which are loading their contents
 *
 * [OUTPUT]
 * - WorkspaceFileTreeItem: One row (folder chevron or spinner, icon, name, size, @ mention, inline rename)
 *   with its expandable children
 * - containerVariants: Stagger animation for a list of rows
 *
 * [POS]
 * Presentation half of WorkspaceFileBrowser: no data fetching and no file operations of its own,
 * everything arrives through props and callbacks.
 */

import React, { memo, useCallback } from 'react';
import { motion, AnimatePresence, type Variants } from 'framer-motion';
import { ChevronRight, RefreshCw } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { FileTypeIcon } from '@/components/features/files/FileTypeIcon';
import type { FileEntry } from '@/services/chat';
import { InlineRenameInput } from './WorkspaceFileOps';
import { REVEAL_ON_HOVER } from '@/lib/utils/a11y';

export const containerVariants: Variants = {
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
  if (bytes === null || bytes === undefined) {
    return '';
  }
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ---------------------------------------------------------------------------
// Tree item
// ---------------------------------------------------------------------------

interface TreeItemProps {
  node: FileEntry;
  depth: number;
  expandedPaths: Set<string>;
  loadingPaths: ReadonlySet<string>;
  onToggle: (node: FileEntry) => void;
  onFileClick?: (file: FileEntry) => void;
  onMention?: (file: FileEntry) => void;
  onContextMenu?: (e: React.MouseEvent, node: FileEntry) => void;
  renamingPath: string | null;
  workspace: string;
  onRenameComplete: () => void;
  onRenameCancel: () => void;
}

export const WorkspaceFileTreeItem: React.FC<TreeItemProps> = memo(
  ({
    node,
    depth,
    expandedPaths,
    loadingPaths,
    onToggle,
    onFileClick,
    onMention,
    onContextMenu,
    renamingPath,
    workspace,
    onRenameComplete,
    onRenameCancel,
  }) => {
    const t = useTranslations('workspace');
    const isDir = node.type === 'directory';
    const children = isDir ? node.children : undefined;
    const isExpanded = expandedPaths.has(node.path);
    const isLoading = loadingPaths.has(node.path);
    const hasChildren = children != null && children.length > 0;
    // `children: null` is a folder the scan did not reach: it can be opened, and opening loads it.
    const canExpand = isDir && (children == null || hasChildren);
    const isRenaming = renamingPath === node.path;

    const handleClick = useCallback(() => {
      if (isDir) {
        onToggle(node);
      } else {
        onFileClick?.(node);
      }
    }, [isDir, node, onToggle, onFileClick]);

    return (
      <motion.div variants={itemVariants}>
        <div
          className="group flex w-full items-center rounded text-sm transition-colors hover:bg-muted/50"
          onContextMenu={(e) => onContextMenu?.(e, node)}
        >
          <button
            type="button"
            className="flex min-w-0 flex-1 items-center gap-1 py-1 pr-2 text-left"
            style={{ paddingLeft: `${depth * 16 + 8}px` }}
            onClick={handleClick}
          >
            <div className="w-4 h-4 flex items-center justify-center shrink-0">
              {isLoading ? (
                <RefreshCw className="h-3 w-3 animate-spin text-muted-foreground" />
              ) : (
                canExpand && (
                  <ChevronRight
                    className={cn('h-3 w-3 text-muted-foreground transition-transform', isExpanded && 'rotate-90')}
                  />
                )
              )}
            </div>

            <FileTypeIcon filename={node.name} isDirectory={isDir} isExpanded={isExpanded} />

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
          </button>

          {!isRenaming && !isDir && onMention && (
            <button
              type="button"
              tabIndex={-1}
              className={cn(
                'shrink-0 self-stretch px-2 text-xs font-semibold text-primary transition-opacity',
                REVEAL_ON_HOVER,
              )}
              title={t('mentionFile')}
              aria-label={t('mentionFile')}
              onClick={() => onMention(node)}
            >
              @
            </button>
          )}
        </div>

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
              {children?.map((child) => (
                <WorkspaceFileTreeItem
                  key={child.path}
                  node={child}
                  depth={depth + 1}
                  expandedPaths={expandedPaths}
                  loadingPaths={loadingPaths}
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
WorkspaceFileTreeItem.displayName = 'WorkspaceFileTreeItem';
