/**
 * [INPUT] DeliverableNode list, activeNodeId, onSelectNode, deliverableType
 * [OUTPUT] DeliverableOutlineNavigator component rendering structural outline / slide thumbnails
 * [POS] artifacts/deliverable-inspector/DeliverableOutlineNavigator.tsx
 */

'use client';

import React, { useState, useMemo } from 'react';
import { Presentation, FileText, Table, Search, Sparkles } from 'lucide-react';
import type {
  DeliverableNode,
  DeliverableType,
  DeliverableNodeType,
} from './deliverableInspectorTypes';

export interface DeliverableOutlineNavigatorProps {
  nodes: DeliverableNode[];
  activeNodeId: string | null;
  onSelectNode: (nodeId: string) => void;
  deliverableType: DeliverableType;
  className?: string;
}

const NODE_ICON_MAP: Record<DeliverableNodeType, React.FC<{ className?: string }>> = {
  slide: Presentation,
  section: FileText,
  sheet: Table,
};

export const DeliverableOutlineNavigator: React.FC<DeliverableOutlineNavigatorProps> = ({
  nodes,
  activeNodeId,
  onSelectNode,
  deliverableType,
  className = '',
}) => {
  const [filterQuery, setFilterQuery] = useState<string>('');

  const filteredNodes = useMemo(() => {
    if (!filterQuery.trim()) {
      return nodes;
    }
    const q = filterQuery.toLowerCase();
    return nodes.filter((n) => {
      return (
        n.title.toLowerCase().includes(q) ||
        n.summary.toLowerCase().includes(q) ||
        `#${n.index}`.includes(q)
      );
    });
  }, [nodes, filterQuery]);

  const typeHeader = useMemo(() => {
    switch (deliverableType) {
      case 'slides':
        return '幻灯片单页大纲';
      case 'document':
      case 'markdown':
        return '文档章节目录';
      case 'spreadsheet':
        return '工作表与分区列表';
      default:
        return '大纲节点导航';
    }
  }, [deliverableType]);

  return (
    <div
      data-testid="deliverable-outline-navigator"
      className={`flex flex-col border-r bg-muted/15 h-full select-none ${className}`}
    >
      {/* Top Header & Search */}
      <div className="p-3 border-b border-border/60 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-foreground tracking-tight">
            {typeHeader}
          </span>
          <span className="text-[11px] font-mono text-muted-foreground bg-muted/60 px-1.5 py-0.5 rounded">
            {nodes.length} 节点
          </span>
        </div>

        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
          <input
            type="text"
            value={filterQuery}
            onChange={(e) => {
              setFilterQuery(e.target.value);
            }}
            placeholder="搜索节点或序号..."
            className="w-full pl-8 pr-2.5 py-1 text-xs rounded-md border border-input bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
      </div>

      {/* Node Items List */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {filteredNodes.length === 0 ? (
          <div className="p-4 text-center text-xs text-muted-foreground">
            未找到匹配的节点
          </div>
        ) : (
          filteredNodes.map((node) => {
            const isActive = node.id === activeNodeId;
            const IconComponent = NODE_ICON_MAP[node.nodeType] || FileText;
            const isPatched = Boolean(node.metadata?.lastPatchedAt);

            return (
              <button
                key={node.id}
                type="button"
                onClick={() => {
                  onSelectNode(node.id);
                }}
                className={`w-full text-left rounded-lg p-2 transition-all flex items-start gap-2.5 border ${
                  isActive
                    ? 'bg-primary/10 border-primary/30 text-primary shadow-xs'
                    : 'bg-card/50 hover:bg-muted/50 border-border/40 text-card-foreground'
                }`}
              >
                <div
                  className={`flex h-6 w-6 shrink-0 items-center justify-center rounded font-mono text-[11px] font-semibold ${
                    isActive
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-muted text-muted-foreground'
                  }`}
                >
                  {node.index}
                </div>

                <div className="min-w-0 flex-1 space-y-0.5">
                  <div className="flex items-center justify-between gap-1">
                    <span className="truncate text-xs font-medium text-foreground flex items-center gap-1">
                      <IconComponent className="h-3 w-3 shrink-0 text-muted-foreground" />
                      {node.title}
                    </span>

                    {isPatched && (
                      <span
                        title="已通过局部补丁更新"
                        className="inline-flex items-center gap-0.5 text-[10px] text-emerald-600 dark:text-emerald-400 shrink-0 font-medium bg-emerald-500/10 px-1 py-0.2 rounded"
                      >
                        <Sparkles className="h-2.5 w-2.5" />
                        已修
                      </span>
                    )}
                  </div>

                  <p className="line-clamp-1 text-[11px] text-muted-foreground">
                    {node.summary}
                  </p>
                </div>
              </button>
            );
          })
        )}
      </div>
    </div>
  );
};
