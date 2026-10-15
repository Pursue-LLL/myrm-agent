/**
 * [INPUT]
 * - react (POS: UI Framework)
 * - lucide-react (POS: Vector Icons)
 * - @/components/features/chat-window/three-pane-studio/threePaneStudioTypes
 * - @/components/features/chat-window/three-pane-studio/useThreePaneStudioStore
 *
 * [OUTPUT]
 * - ContextTreePane (POS: Left pane hierarchical context tree component)
 *
 * [POS]
 * Visual tree navigator for Item 198 (P0): ThreePaneContextStudioAndRealtimeToolHighlightSuite.
 * Renders User Memory, Workspace Resources, and Agent Skills with realtime pulse highlights,
 * expansion toggles, and one-click reference injection into the chat prompt.
 */

import React from 'react';
import {
  ChevronRight,
  ChevronDown,
  Brain,
  FileCode,
  Folder,
  FolderOpen,
  Wrench,
  CornerDownLeft,
  Layers,
} from 'lucide-react';
import type {
  ContextTreeNode,
  ContextNodeType,
  NodeStatus,
} from './threePaneStudioTypes';
import { useThreePaneStudioStore } from './useThreePaneStudioStore';

export interface ContextTreePaneProps {
  readonly onSelectNode?: (node: ContextTreeNode) => void;
  readonly onInsertReference?: (node: ContextTreeNode) => void;
  readonly className?: string;
}

export const ContextTreePane: React.FC<ContextTreePaneProps> = ({
  onSelectNode,
  onInsertReference,
  className = '',
}) => {
  const {
    rootNodes,
    selectedNodeId,
    expandedNodeIds,
    toggleNodeExpanded,
    selectNode,
  } = useThreePaneStudioStore();

  const handleNodeClick = (node: ContextTreeNode) => {
    if (node.children && node.children.length > 0) {
      toggleNodeExpanded(node.id);
    }
    selectNode(node.id);
    if (onSelectNode) {
      onSelectNode(node);
    }
  };

  const handleReferenceClick = (e: React.MouseEvent, node: ContextTreeNode) => {
    e.stopPropagation();
    if (onInsertReference) {
      onInsertReference(node);
    }
  };

  const getNodeIcon = (node: ContextTreeNode, isExpanded: boolean) => {
    if (node.children && node.children.length > 0) {
      return isExpanded ? (
        <FolderOpen className="w-3.5 h-3.5 text-amber-400 shrink-0" />
      ) : (
        <Folder className="w-3.5 h-3.5 text-amber-400 shrink-0" />
      );
    }

    const typeIconMap: Record<ContextNodeType, React.ReactElement> = {
      user_memory: <Brain className="w-3.5 h-3.5 text-purple-400 shrink-0" />,
      resource: <FileCode className="w-3.5 h-3.5 text-cyan-400 shrink-0" />,
      skill: <Wrench className="w-3.5 h-3.5 text-emerald-400 shrink-0" />,
    };

    return typeIconMap[node.type];
  };

  const renderStatusBadge = (status?: NodeStatus) => {
    if (!status || status === 'idle') {
      return null;
    }

    if (status === 'reading') {
      return (
        <span
          data-testid="status-badge-reading"
          className="px-1 py-0.2 text-[9px] font-mono rounded bg-cyan-950 text-cyan-300 border border-cyan-800"
        >
          读取中
        </span>
      );
    }

    if (status === 'writing') {
      return (
        <span
          data-testid="status-badge-writing"
          className="px-1 py-0.2 text-[9px] font-mono rounded bg-amber-950 text-amber-300 border border-amber-800"
        >
          写入中
        </span>
      );
    }

    return (
      <span
        data-testid="status-badge-modified"
        className="px-1 py-0.2 text-[9px] font-mono rounded bg-emerald-950 text-emerald-300 border border-emerald-800"
      >
        已修改
      </span>
    );
  };

  const renderNode = (node: ContextTreeNode, depth = 0) => {
    const hasChildren = Boolean(node.children && node.children.length > 0);
    const isExpanded = expandedNodeIds.includes(node.id);
    const isSelected = selectedNodeId === node.id;
    const isHighlighted = Boolean(node.activeHighlight);

    return (
      <div key={node.id} className="flex flex-col select-none">
        <div
          data-testid={`tree-node-${node.id}`}
          style={{ paddingLeft: `${depth * 14 + 8}px` }}
          className={`flex items-center justify-between group py-1 pr-2 rounded text-xs transition-colors ${
            isHighlighted
              ? 'bg-cyan-950/60 text-cyan-200 ring-1 ring-cyan-500 animate-pulse font-medium'
              : isSelected
                ? 'bg-slate-800/90 text-slate-100 font-medium'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/40'
          }`}
        >
          {hasChildren ? (
            <button
              type="button"
              data-testid={`toggle-expand-${node.id}`}
              aria-label={isExpanded ? '折叠目录' : '展开目录'}
              onClick={(e) => {
                e.stopPropagation();
                toggleNodeExpanded(node.id);
              }}
              className="p-0.5 rounded hover:bg-slate-700/60 text-slate-500 hover:text-slate-300 transition-colors shrink-0 mr-1"
            >
              {isExpanded ? (
                <ChevronDown className="w-3 h-3" />
              ) : (
                <ChevronRight className="w-3 h-3" />
              )}
            </button>
          ) : (
            <span className="w-4 shrink-0 mr-1" />
          )}

          <button
            type="button"
            data-testid={`btn-select-node-${node.id}`}
            onClick={() => handleNodeClick(node)}
            className="flex-1 flex items-center gap-1.5 min-w-0 truncate text-left focus:outline-none"
          >
            {getNodeIcon(node, isExpanded)}
            <span className="truncate text-[11px]" title={node.path}>
              {node.label}
            </span>
          </button>

          <div className="flex items-center gap-1 shrink-0 ml-2">
            {renderStatusBadge(node.status)}

            {onInsertReference && !hasChildren && (
              <button
                type="button"
                data-testid={`btn-reference-${node.id}`}
                aria-label="引用到会话"
                title="一键引用此上下文至对话输入框"
                onClick={(e) => handleReferenceClick(e, node)}
                className="opacity-0 group-hover:opacity-100 p-0.5 rounded text-slate-400 hover:text-cyan-300 hover:bg-slate-700/60 transition-opacity"
              >
                <CornerDownLeft className="w-3 h-3" />
              </button>
            )}
          </div>
        </div>

        {hasChildren && isExpanded && node.children && (
          <div className="flex flex-col">
            {node.children.map((child) => renderNode(child, depth + 1))}
          </div>
        )}
      </div>
    );
  };

  return (
    <aside
      data-testid="context-tree-pane"
      className={`flex flex-col h-full bg-slate-900 border-r border-slate-800/80 overflow-y-auto scrollbar-thin ${className}`}
    >
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-800/80 bg-slate-950/40 shrink-0">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-300">
          <Layers className="w-3.5 h-3.5 text-cyan-400" />
          <span>统一上下文树</span>
        </div>
        <span className="text-[10px] text-slate-500 font-mono">OpenViking Mode</span>
      </div>

      <nav aria-label="上下文层级目录" className="flex flex-col p-1.5 gap-0.5">
        {rootNodes.map((rootNode) => renderNode(rootNode, 0))}
      </nav>
    </aside>
  );
};
