/**
 * [INPUT]
 * - react (POS: UI 组件与内部树状态)
 * - lucide-react (POS: 矢量图标库)
 * - @/lib/utils/classnameUtils::cn (POS: Tailwind 样式合并纯函数)
 *
 * [OUTPUT]
 * - AgentHierarchyTreeView: 智能体创建层级树与血统溯源组件
 * - AgentHierarchyTreeViewProps: 组件属性契约
 * - AgentHierarchyNode: 树节点数据契约
 * - AgentProvenance: 创建血统元数据契约
 * - CreatorType: 创建者类别枚举联合
 *
 * [POS]
 * 智能体创建层级与来源追溯树状视图（AgentCreationHierarchyProvenance）。
 * 清晰呈现「谁创建了谁」、创建来源胶囊、祖先链条与多级父子组织树。
 */
import React, { useState } from 'react';
import {
  GitFork,
  Bot,
  User,
  FileCode,
  Settings,
  ChevronRight,
  ChevronDown,
  RefreshCw,
  Search,
  Layers,
  ArrowRight,
} from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';

export type CreatorType = 'user' | 'agent' | 'script' | 'system';

export interface AgentProvenance {
  agentId: string;
  creatorType: CreatorType;
  creatorId: string;
  parentAgentId?: string | null;
  createdAt?: number;
  ancestryPath?: string[];
}

export interface AgentHierarchyNode {
  agentId: string;
  name: string;
  description?: string;
  avatar?: string | null;
  agentType?: string;
  provenance: AgentProvenance;
  depth: number;
  children?: AgentHierarchyNode[];
}

export interface AgentHierarchyTreeViewProps {
  roots: AgentHierarchyNode[];
  totalNodes?: number;
  maxDepth?: number;
  isLoading?: boolean;
  onSelectAgent?: (agentId: string) => void;
  onRefresh?: () => Promise<void> | void;
  className?: string;
}

function getCreatorBadge(creatorType: CreatorType, creatorId: string): React.ReactElement {
  switch (creatorType) {
    case 'agent':
      return (
        <span
          data-testid="creator-badge-agent"
          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20"
        >
          <Bot className="w-3 h-3 text-purple-500" />
          <span>衍生自 @{creatorId}</span>
        </span>
      );
    case 'script':
      return (
        <span
          data-testid="creator-badge-script"
          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20"
        >
          <FileCode className="w-3 h-3 text-amber-500" />
          <span>脚本 {creatorId}</span>
        </span>
      );
    case 'system':
      return (
        <span
          data-testid="creator-badge-system"
          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-muted text-muted-foreground border border-border"
        >
          <Settings className="w-3 h-3" />
          <span>系统预设</span>
        </span>
      );
    case 'user':
    default:
      return (
        <span
          data-testid="creator-badge-user"
          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20"
        >
          <User className="w-3 h-3 text-blue-500" />
          <span>用户创建</span>
        </span>
      );
  }
}

interface TreeNodeItemProps {
  node: AgentHierarchyNode;
  searchQuery: string;
  expandedMap: Record<string, boolean>;
  onToggleExpand: (id: string) => void;
  onSelectAgent?: (id: string) => void;
}

const TreeNodeItem: React.FC<TreeNodeItemProps> = ({
  node,
  searchQuery,
  expandedMap,
  onToggleExpand,
  onSelectAgent,
}) => {
  const hasChildren = Boolean(node.children && node.children.length > 0);
  const isExpanded = expandedMap[node.agentId] ?? true;

  const matchesSearch =
    !searchQuery ||
    node.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    node.agentId.toLowerCase().includes(searchQuery.toLowerCase());

  return (
    <div className="space-y-1">
      <div
        data-testid={`tree-node-${node.agentId}`}
        style={{ paddingLeft: `${node.depth * 20}px` }}
        className={cn(
          'flex items-center justify-between gap-2 p-2 rounded-lg border border-border/60 bg-background/50 hover:bg-muted/50 transition-colors text-xs',
          matchesSearch && searchQuery && 'ring-1 ring-primary bg-primary/5'
        )}
      >
        <div className="flex items-center gap-2 flex-1 min-w-0">
          {hasChildren ? (
            <button
              type="button"
              data-testid={`toggle-node-${node.agentId}`}
              onClick={() => onToggleExpand(node.agentId)}
              className="p-0.5 text-muted-foreground hover:text-foreground rounded"
            >
              {isExpanded ? (
                <ChevronDown className="w-3.5 h-3.5" />
              ) : (
                <ChevronRight className="w-3.5 h-3.5" />
              )}
            </button>
          ) : (
            <span className="w-4.5 inline-block" />
          )}

          <button
            type="button"
            onClick={() => onSelectAgent?.(node.agentId)}
            className="flex items-center gap-2 text-left cursor-pointer flex-1 min-w-0 bg-transparent border-0 p-0"
          >
            <div className="w-6 h-6 rounded-md bg-primary/10 text-primary flex items-center justify-center font-bold text-[10px] shrink-0 overflow-hidden">
              {node.avatar ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={node.avatar} alt={node.name} className="w-full h-full object-cover" />
              ) : (
                node.name.slice(0, 1).toUpperCase()
              )}
            </div>
            <div className="truncate">
              <span className="font-semibold text-foreground">{node.name}</span>
              <span className="text-[11px] font-mono text-muted-foreground ml-1.5 opacity-75">
                ({node.agentId})
              </span>
            </div>
          </button>
        </div>

        {/* Provenance Badge & Ancestry Path */}
        <div className="flex items-center gap-2 shrink-0">
          {node.provenance.ancestryPath && node.provenance.ancestryPath.length > 0 && (
            <div
              data-testid={`ancestry-path-${node.agentId}`}
              className="hidden md:flex items-center gap-1 text-[10px] font-mono text-muted-foreground/80 bg-muted/40 px-1.5 py-0.5 rounded border border-border/40"
              title={`祖先链条: ${node.provenance.ancestryPath.join(' -> ')}`}
            >
              <span>{node.provenance.ancestryPath[0]}</span>
              <ArrowRight className="w-2.5 h-2.5" />
              <span>{node.agentId}</span>
            </div>
          )}

          {getCreatorBadge(node.provenance.creatorType, node.provenance.creatorId)}

          {hasChildren && (
            <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-muted text-muted-foreground">
              {node.children?.length} 子智能体
            </span>
          )}
        </div>
      </div>

      {/* Recursive Children Rendering */}
      {hasChildren && isExpanded && (
        <div className="space-y-1">
          {node.children?.map((child) => (
            <TreeNodeItem
              key={child.agentId}
              node={child}
              searchQuery={searchQuery}
              expandedMap={expandedMap}
              onToggleExpand={onToggleExpand}
              onSelectAgent={onSelectAgent}
            />
          ))}
        </div>
      )}
    </div>
  );
};

export const AgentHierarchyTreeView: React.FC<AgentHierarchyTreeViewProps> = ({
  roots,
  totalNodes,
  maxDepth = 0,
  isLoading = false,
  onSelectAgent,
  onRefresh,
  className,
}) => {
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [expandedMap, setExpandedMap] = useState<Record<string, boolean>>({});

  const total = totalNodes ?? roots.reduce((acc, r) => acc + 1 + (r.children?.length || 0), 0);

  const toggleExpand = (id: string): void => {
    setExpandedMap((prev) => ({
      ...prev,
      [id]: !(prev[id] ?? true),
    }));
  };

  const expandAll = (): void => {
    const nextMap: Record<string, boolean> = {};
    const traverse = (nodes: AgentHierarchyNode[]): void => {
      for (const n of nodes) {
        nextMap[n.agentId] = true;
        if (n.children) {
          traverse(n.children);
        }
      }
    };
    traverse(roots);
    setExpandedMap(nextMap);
  };

  const collapseAll = (): void => {
    const nextMap: Record<string, boolean> = {};
    const traverse = (nodes: AgentHierarchyNode[]): void => {
      for (const n of nodes) {
        nextMap[n.agentId] = false;
        if (n.children) {
          traverse(n.children);
        }
      }
    };
    traverse(roots);
    setExpandedMap(nextMap);
  };

  return (
    <div
      data-testid="agent-hierarchy-tree-view"
      className={cn(
        'rounded-xl border border-border bg-card p-4 shadow-sm space-y-3',
        className
      )}
    >
      {/* Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 pb-3">
        <div className="flex items-center gap-2">
          <div className="p-2 rounded-lg bg-primary/10 text-primary">
            <GitFork className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
              智能体创建层级与来源追溯
              <span className="text-xs font-normal text-muted-foreground font-mono">
                ({total} 节点, 最大深度 {maxDepth})
              </span>
            </h3>
            <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5">
              <span>顶级根节点 {roots.length}</span>
              <span>•</span>
              <span className="flex items-center gap-1">
                <Layers className="w-3 h-3 text-primary inline" />
                防循环衍生保护激活
              </span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          <button
            type="button"
            data-testid="expand-all-btn"
            onClick={expandAll}
            className="px-2 py-1 text-xs rounded border border-border hover:bg-muted text-muted-foreground transition-colors"
          >
            展开全部
          </button>
          <button
            type="button"
            data-testid="collapse-all-btn"
            onClick={collapseAll}
            className="px-2 py-1 text-xs rounded border border-border hover:bg-muted text-muted-foreground transition-colors"
          >
            折叠全部
          </button>
          {onRefresh && (
            <button
              type="button"
              data-testid="refresh-hierarchy-btn"
              disabled={isLoading}
              onClick={() => void onRefresh()}
              className="p-1.5 text-muted-foreground hover:text-foreground transition-colors rounded-lg hover:bg-muted"
              title="刷新层级树"
            >
              <RefreshCw className={cn('w-4 h-4', isLoading && 'animate-spin')} />
            </button>
          )}
        </div>
      </div>

      {/* Search Bar */}
      <div className="relative">
        <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-muted-foreground" />
        <input
          type="text"
          data-testid="hierarchy-search-input"
          placeholder="搜索智能体名称或 ID..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full pl-8 pr-2 py-1.5 text-xs rounded border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
        />
      </div>

      {/* Tree Content */}
      {roots.length === 0 ? (
        <div
          data-testid="empty-hierarchy-state"
          className="text-center py-8 px-4 rounded-lg border border-dashed border-border"
        >
          <Bot className="w-8 h-8 text-muted-foreground/60 mx-auto mb-2" />
          <p className="text-xs font-medium text-foreground">暂无智能体层级数据</p>
          <p className="text-[11px] text-muted-foreground mt-1">
            系统中的智能体创建衍生关系将自动在此构建无环树状视图
          </p>
        </div>
      ) : (
        <div className="space-y-1.5 max-h-96 overflow-y-auto pr-1" data-testid="hierarchy-forest">
          {roots.map((root) => (
            <TreeNodeItem
              key={root.agentId}
              node={root}
              searchQuery={searchQuery}
              expandedMap={expandedMap}
              onToggleExpand={toggleExpand}
              onSelectAgent={onSelectAgent}
            />
          ))}
        </div>
      )}
    </div>
  );
};
