/**
 * CLI 工作区文件目录树组件
 *
 * 1. 本文件的 INPUT/OUTPUT/POS 注释
 * 2. 所属文件夹的 _ARCH.md
 *
 * [INPUT]
 * - workspacePath: 工作区路径
 * - files: 文件列表（可选，用于手动传入）
 * - onFileClick: 文件点击回调
 * - onFileDoubleClick: 文件双击回调
 *
 * [OUTPUT]
 * - CLIWorkspaceTree: 文件目录树组件
 *   - 递归展示文件夹结构
 *   - 支持展开/折叠
 *   - 文件类型图标
 *
 * [POS]
 * CLI 可视化工具的文件目录树组件。显示工作区的文件结构，
 * 支持点击预览和双击打开。仅在 Tauri 桌面环境使用。
 */

'use client';

import React, { memo, useState, useCallback } from 'react';
import { motion, AnimatePresence, type Variants } from 'framer-motion';
import { ChevronRight, RefreshCw, FolderOpen } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { CLIFileIcon } from './CLIFileIcon';

/** 文件节点类型 */
export interface FileNode {
  name: string;
  path: string;
  type: 'file' | 'directory';
  size?: number;
  children?: FileNode[];
}

export interface CLIWorkspaceTreeProps {
  /** 工作区路径 */
  workspacePath: string;
  /** 文件列表（可选） */
  files?: FileNode[];
  /** 文件点击回调 */
  onFileClick?: (file: FileNode) => void;
  /** 文件双击回调 */
  onFileDoubleClick?: (file: FileNode) => void;
  /** 文件右键回调 */
  onFileRightClick?: (file: FileNode, event: React.MouseEvent) => void;
  /** 刷新回调 */
  onRefresh?: () => void;
  /** 是否正在加载 */
  loading?: boolean;
  /** 类名 */
  className?: string;
}

/** 动画变体 */
const containerVariants: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.02,
      delayChildren: 0.01,
    },
  },
  exit: {
    opacity: 0,
    transition: {
      staggerChildren: 0.01,
      staggerDirection: -1,
    },
  },
};

const itemVariants: Variants = {
  hidden: { opacity: 0, x: -8 },
  visible: {
    opacity: 1,
    x: 0,
    transition: { duration: 0.12, ease: 'easeOut' },
  },
  exit: {
    opacity: 0,
    x: -8,
    transition: { duration: 0.08, ease: 'easeIn' },
  },
};

/** 文件大小格式化 */
function formatFileSize(bytes?: number): string {
  if (bytes === undefined) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** 单个文件/目录项 */
interface TreeItemProps {
  node: FileNode;
  depth: number;
  expandedPaths: Set<string>;
  onToggleExpand: (path: string) => void;
  onFileClick?: (file: FileNode) => void;
  onFileDoubleClick?: (file: FileNode) => void;
  onFileRightClick?: (file: FileNode, event: React.MouseEvent) => void;
}

const TreeItem: React.FC<TreeItemProps> = memo(
  ({ node, depth, expandedPaths, onToggleExpand, onFileClick, onFileDoubleClick, onFileRightClick }) => {
    const isDirectory = node.type === 'directory';
    const isExpanded = expandedPaths.has(node.path);
    const hasChildren = isDirectory && node.children && node.children.length > 0;

    const handleClick = useCallback(() => {
      if (isDirectory && hasChildren) {
        onToggleExpand(node.path);
      } else if (!isDirectory) {
        onFileClick?.(node);
      }
    }, [isDirectory, hasChildren, node, onToggleExpand, onFileClick]);

    const handleDoubleClick = useCallback(() => {
      if (!isDirectory) {
        onFileDoubleClick?.(node);
      }
    }, [isDirectory, node, onFileDoubleClick]);

    const handleRightClick = useCallback(
      (event: React.MouseEvent) => {
        event.preventDefault();
        onFileRightClick?.(node, event);
      },
      [node, onFileRightClick],
    );

    return (
      <motion.div variants={itemVariants}>
        {/* 当前项 */}
        <div
          className={cn(
            'flex items-center gap-1 py-1 px-2 rounded cursor-pointer',
            'hover:bg-muted/50 transition-colors group',
          )}
          style={{ paddingLeft: `${depth * 16 + 8}px` }}
          onClick={handleClick}
          onDoubleClick={handleDoubleClick}
          onContextMenu={handleRightClick}
        >
          {/* 展开箭头 */}
          <div className="w-4 h-4 flex items-center justify-center">
            {hasChildren && (
              <ChevronRight
                className={cn('h-3 w-3 text-muted-foreground transition-transform', isExpanded && 'rotate-90')}
              />
            )}
          </div>

          {/* 图标 */}
          <CLIFileIcon filename={node.name} isDirectory={isDirectory} isExpanded={isExpanded} />

          {/* 名称 */}
          <span className="text-sm truncate flex-1" title={node.name}>
            {node.name}
          </span>

          {/* 文件大小 */}
          {!isDirectory && node.size !== undefined && (
            <span className="text-xs text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity">
              {formatFileSize(node.size)}
            </span>
          )}
        </div>

        {/* 子项 */}
        <AnimatePresence>
          {isExpanded && hasChildren && (
            <motion.div
              variants={containerVariants}
              initial="hidden"
              animate="visible"
              exit="exit"
              className="relative"
            >
              {/* 连接线 */}
              <div
                className="absolute left-0 top-0 bottom-0 border-l border-border/50"
                style={{ marginLeft: `${depth * 16 + 16}px` }}
              />
              {node.children!.map((child) => (
                <TreeItem
                  key={child.path}
                  node={child}
                  depth={depth + 1}
                  expandedPaths={expandedPaths}
                  onToggleExpand={onToggleExpand}
                  onFileClick={onFileClick}
                  onFileDoubleClick={onFileDoubleClick}
                  onFileRightClick={onFileRightClick}
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

/**
 * CLI 工作区文件目录树组件
 */
export const CLIWorkspaceTree: React.FC<CLIWorkspaceTreeProps> = memo(
  ({
    workspacePath,
    files,
    onFileClick,
    onFileDoubleClick,
    onFileRightClick,
    onRefresh,
    loading = false,
    className,
  }) => {
    const [expandedPaths, setExpandedPaths] = useState<Set<string>>(new Set());

    // 切换展开状态
    const handleToggleExpand = useCallback((path: string) => {
      setExpandedPaths((prev) => {
        const next = new Set(prev);
        if (next.has(path)) {
          next.delete(path);
        } else {
          next.add(path);
        }
        return next;
      });
    }, []);

    // 获取工作区名称
    const workspaceName = workspacePath.split('/').pop() || workspacePath;

    return (
      <div className={cn('flex flex-col h-full', className)}>
        {/* Header */}
        <div className="flex items-center justify-between px-3 py-2 border-b border-border">
          <div className="flex items-center gap-2">
            <FolderOpen className="h-4 w-4 text-amber-500" />
            <span className="text-sm font-medium truncate" title={workspacePath}>
              {workspaceName}
            </span>
          </div>
          {onRefresh && (
            <button
              onClick={onRefresh}
              disabled={loading}
              className={cn('p-1 rounded hover:bg-muted transition-colors', loading && 'animate-spin')}
              title="Refresh"
            >
              <RefreshCw className="h-4 w-4" />
            </button>
          )}
        </div>

        {/* Tree Content */}
        <div className="flex-1 overflow-auto py-2">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <RefreshCw className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : !files || files.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
              <FolderOpen className="h-8 w-8 mb-2" />
              <span className="text-sm">Empty workspace</span>
            </div>
          ) : (
            <motion.div variants={containerVariants} initial="hidden" animate="visible">
              {files.map((node) => (
                <TreeItem
                  key={node.path}
                  node={node}
                  depth={0}
                  expandedPaths={expandedPaths}
                  onToggleExpand={handleToggleExpand}
                  onFileClick={onFileClick}
                  onFileDoubleClick={onFileDoubleClick}
                  onFileRightClick={onFileRightClick}
                />
              ))}
            </motion.div>
          )}
        </div>
      </div>
    );
  },
);

CLIWorkspaceTree.displayName = 'CLIWorkspaceTree';

export default CLIWorkspaceTree;
