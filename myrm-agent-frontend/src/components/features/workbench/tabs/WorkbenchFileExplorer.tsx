'use client';

/**
 * [INPUT]
 * - fetchWorkspaceFiles, fetchFileContent from @/services/workbench
 * - useWorkbenchStore from @/store/useWorkbenchStore
 * - useTranslations from next-intl (namespace: 'workbench.files')
 *
 * [OUTPUT]
 * - WorkbenchFileExplorer: Directory tree explorer of one chat's workspace with quick search & file preview
 *
 * [POS]
 * Auxiliary Workbench File Explorer tab component.
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import {
  Folder,
  FolderOpen,
  FileText,
  Search,
  RefreshCw,
  Code,
  FileCode,
  ChevronRight,
  ChevronDown,
} from 'lucide-react';
import {
  fetchWorkspaceFiles,
  fetchFileContent,
  type WorkbenchFileNode,
} from '@/services/workbench';
import { useWorkbenchStore } from '@/store/useWorkbenchStore';

interface FileTreeNodeProps {
  node: WorkbenchFileNode;
  level: number;
  onSelect: (node: WorkbenchFileNode) => void;
  selectedPath: string | null;
  expandedDirs: Set<string>;
  onToggleDir: (path: string) => void;
}

function FileTreeNodeItem({
  node,
  level,
  onSelect,
  selectedPath,
  expandedDirs,
  onToggleDir,
}: FileTreeNodeProps) {
  const isDir = node.node_type === 'directory';
  const isExpanded = expandedDirs.has(node.path);
  const isSelected = selectedPath === node.path;

  const handleClick = () => {
    if (isDir) {
      onToggleDir(node.path);
    } else {
      onSelect(node);
    }
  };

  return (
    <div className="flex flex-col select-none">
      <button
        type="button"
        onClick={handleClick}
        className={`flex items-center gap-1.5 px-2 py-1 text-xs rounded-md transition-colors text-left w-full ${
          isSelected
            ? 'bg-primary/15 text-primary font-medium'
            : 'text-foreground/85 hover:bg-muted/60'
        }`}
        style={{ paddingLeft: `${Math.max(8, level * 14)}px` }}
      >
        {isDir ? (
          <>
            <span className="text-muted-foreground w-3.5 h-3.5 flex items-center justify-center">
              {isExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
            </span>
            {isExpanded ? (
              <FolderOpen className="w-3.5 h-3.5 text-primary shrink-0" />
            ) : (
              <Folder className="w-3.5 h-3.5 text-primary/80 shrink-0" />
            )}
          </>
        ) : (
          <>
            <span className="w-3.5" />
            {node.extension === 'ts' || node.extension === 'tsx' || node.extension === 'py' ? (
              <FileCode className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
            ) : (
              <FileText className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
            )}
          </>
        )}
        <span className="truncate">{node.name}</span>
        {!isDir && node.size_bytes > 0 && (
          <span className="ml-auto text-[10px] font-mono text-muted-foreground/70">
            {Math.round(node.size_bytes / 1024)}k
          </span>
        )}
      </button>

      {isDir && isExpanded && node.children && node.children.length > 0 && (
        <div className="flex flex-col">
          {node.children.map((child) => (
            <FileTreeNodeItem
              key={child.path}
              node={child}
              level={level + 1}
              onSelect={onSelect}
              selectedPath={selectedPath}
              expandedDirs={expandedDirs}
              onToggleDir={onToggleDir}
            />
          ))}
        </div>
      )}
    </div>
  );
}

interface WorkbenchFileExplorerProps {
  chatId: string;
}

export function WorkbenchFileExplorer({ chatId }: WorkbenchFileExplorerProps) {
  const t = useTranslations('workbench.files');
  const [rootNodes, setRootNodes] = useState<WorkbenchFileNode[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isUnavailable, setIsUnavailable] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(new Set());

  const selectedFilePath = useWorkbenchStore((s) => s.selectedFilePath);
  const selectedFileContent = useWorkbenchStore((s) => s.selectedFileContent);
  const setSelectedFile = useWorkbenchStore((s) => s.setSelectedFile);

  const loadTree = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await fetchWorkspaceFiles(chatId, undefined, 3);
      setRootNodes(data.nodes);
      setIsUnavailable(false);
    } catch {
      setRootNodes([]);
      setIsUnavailable(true);
    } finally {
      setIsLoading(false);
    }
  }, [chatId]);

  useEffect(() => {
    void loadTree();
  }, [loadTree]);

  const handleToggleDir = useCallback((path: string) => {
    setExpandedDirs((prev) => {
      const next = new Set(prev);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  }, []);

  const handleSelectFile = useCallback(
    async (node: WorkbenchFileNode) => {
      const { sessionEpoch } = useWorkbenchStore.getState();
      setSelectedFile(node.path, null);
      // A reply only lands while its file is still the selection of the same session:
      // a later click or a chat switch supersedes it.
      const isCurrent = (): boolean => {
        const state = useWorkbenchStore.getState();
        return state.sessionEpoch === sessionEpoch && state.selectedFilePath === node.path;
      };
      try {
        const content = await fetchFileContent(chatId, node.path);
        if (isCurrent()) {
          setSelectedFile(node.path, content);
        }
      } catch {
        if (isCurrent()) {
          setSelectedFile(null, null);
        }
      }
    },
    [chatId, setSelectedFile],
  );

  // Filter nodes by query
  const filteredNodes = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) {
      return rootNodes;
    }

    const filterRecursive = (nodes: WorkbenchFileNode[]): WorkbenchFileNode[] => {
      const result: WorkbenchFileNode[] = [];
      for (const n of nodes) {
        if (n.name.toLowerCase().includes(q) || n.path.toLowerCase().includes(q)) {
          result.push(n);
        } else if (n.node_type === 'directory' && n.children) {
          const matchingChildren = filterRecursive(n.children);
          if (matchingChildren.length > 0) {
            result.push({ ...n, children: matchingChildren });
          }
        }
      }
      return result;
    };

    return filterRecursive(rootNodes);
  }, [rootNodes, searchQuery]);

  return (
    <div className="flex flex-col h-full overflow-hidden text-foreground">
      {/* Search Header */}
      <div className="p-2 border-b border-border/60 flex items-center gap-1.5 bg-card/60">
        <div className="relative flex-1">
          <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
          <input
            type="search"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t('searchPlaceholder')}
            className="w-full pl-8 pr-2.5 py-1 text-xs rounded-lg bg-background border border-border/70 focus:outline-hidden focus:ring-1 focus:ring-primary"
          />
        </div>
        <button
          type="button"
          onClick={() => void loadTree()}
          disabled={isLoading}
          aria-label={t('refreshAction')}
          className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Main Body: Split view of Tree + Quick Code Preview */}
      <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
        {/* Tree List */}
        <div className="w-full md:w-56 border-b md:border-b-0 md:border-r border-border/60 overflow-y-auto p-1.5 max-h-48 md:max-h-full">
          {isLoading && rootNodes.length === 0 ? (
            <div className="p-4 text-center text-xs text-muted-foreground">
              {t('loadingTree')}
            </div>
          ) : filteredNodes.length === 0 ? (
            <div className="p-4 text-center text-xs text-muted-foreground">
              {isUnavailable ? t('workspaceUnavailable') : t('emptyResults')}
            </div>
          ) : (
            filteredNodes.map((node) => (
              <FileTreeNodeItem
                key={node.path}
                node={node}
                level={0}
                onSelect={handleSelectFile}
                selectedPath={selectedFilePath}
                expandedDirs={expandedDirs}
                onToggleDir={handleToggleDir}
              />
            ))
          )}
        </div>

        {/* Code Preview Surface */}
        <div className="flex-1 flex flex-col overflow-hidden bg-background/50">
          {selectedFileContent ? (
            <>
              <div className="px-3 py-1.5 border-b border-border/40 flex items-center justify-between text-xs bg-muted/20">
                <div className="flex items-center gap-1.5 font-mono truncate">
                  <Code className="w-3.5 h-3.5 text-primary shrink-0" />
                  <span className="font-semibold">{selectedFileContent.path}</span>
                </div>
                {!selectedFileContent.is_binary && (
                  <div className="flex items-center gap-2 text-[10px] text-muted-foreground font-mono">
                    <span className="uppercase px-1.5 py-0.5 rounded bg-muted">
                      {selectedFileContent.language}
                    </span>
                    {!selectedFileContent.truncated && (
                      <span>{t('lineCount', { count: selectedFileContent.content.split('\n').length })}</span>
                    )}
                  </div>
                )}
              </div>

              {selectedFileContent.truncated && (
                <div className="px-3 py-1 border-b border-border/40 text-[10px] text-muted-foreground bg-muted/30">
                  {t('previewTruncated')}
                </div>
              )}

              {selectedFileContent.is_binary ? (
                <div className="flex-1 flex items-center justify-center p-6 text-center text-xs text-muted-foreground">
                  {t('binaryFile')}
                </div>
              ) : (
                <div className="flex-1 p-3 overflow-auto font-mono text-[11px] leading-relaxed text-foreground/90 whitespace-pre">
                  {selectedFileContent.content}
                </div>
              )}
            </>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-xs text-muted-foreground gap-1.5 p-6">
              <FileText className="w-8 h-8 opacity-40" />
              <span>{t('selectFileHint')}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
