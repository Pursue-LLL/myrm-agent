'use client';

/**
 * [INPUT]
 * - ./types::RetrievalTreeNode, PruningReason (POS: 决策树契约)
 * - lucide-react::ChevronRight, ChevronDown, CheckCircle2, Scissors, Folder, FolderOpen, FileText, Sparkles, HelpCircle (POS: 视觉指示图标)
 *
 * [OUTPUT]
 * - RetrievalDecisionTreeView: 上下文检索分层下钻决策树与剪枝留痕可视化组件
 *
 * [POS]
 * src/components/features/system-monitor/RetrievalDecisionTreeView.tsx — 检索下钻决策树与剪枝可视化树状视图。
 */

import React, { useState } from 'react';
import {
  ChevronRight,
  ChevronDown,
  CheckCircle2,
  Scissors,
  Folder,
  FolderOpen,
  FileText,
  Sparkles,
  HelpCircle,
} from 'lucide-react';
import type { RetrievalTreeNode, PruningReason } from './types';

interface RetrievalDecisionTreeViewProps {
  nodes: RetrievalTreeNode[];
  className?: string;
  defaultExpanded?: boolean;
}

const PRUNING_LABELS: Record<PruningReason, { label: string; desc: string }> = {
  none: { label: '未剪枝', desc: '正常候选节点' },
  score_below_threshold: { label: '分值低于阈值', desc: '相似度得分未达到判定底线' },
  topk_overflow: { label: 'Top-K 溢出', desc: '分值达标但超出召回配额上限' },
  semantic_dedup: { label: '语义冗余去重', desc: '与已有命中段落高维重合' },
  policy_blocked: { label: '安全策略拦截', desc: '合规与敏感词策略防御丢弃' },
  unknown: { label: '未明剪枝', desc: '内部规则截断' },
};

interface TreeNodeItemProps {
  node: RetrievalTreeNode;
  isExpanded: boolean;
  onToggle: (nodeId: string) => void;
  expandedMap: Record<string, boolean>;
}

const TreeNodeItem: React.FC<TreeNodeItemProps> = ({
  node,
  isExpanded,
  onToggle,
  expandedMap,
}) => {
  const hasChildren = node.children && node.children.length > 0;
  const isPruned = node.is_pruned;
  const isHit = node.is_hit;

  let statusBg = 'bg-background hover:bg-muted/40 text-foreground';
  let badgeColor = 'bg-muted text-muted-foreground border-border';

  if (isHit) {
    statusBg = 'bg-emerald-500/10 hover:bg-emerald-500/15 text-emerald-950 dark:text-emerald-100 border-emerald-500/30';
    badgeColor = 'bg-emerald-500/20 text-emerald-700 dark:text-emerald-300 border-emerald-500/40';
  } else if (isPruned) {
    statusBg = 'bg-muted/30 opacity-75 text-muted-foreground border-dashed border-border';
    badgeColor = 'bg-destructive/15 text-destructive dark:text-red-400 border-destructive/30';
  }

  const pruningMeta = PRUNING_LABELS[node.pruning_reason] || PRUNING_LABELS.unknown;

  return (
    <div className="select-none text-xs">
      <div
        className={`flex items-center gap-2 px-2.5 py-1.5 rounded-lg border transition-colors mb-1 ${statusBg}`}
        style={{ marginLeft: `${node.depth * 18}px` }}
      >
        {/* 折叠/展开控制 */}
        {hasChildren ? (
          <button
            type="button"
            onClick={() => onToggle(node.node_id)}
            aria-label={isExpanded ? '折叠子目录' : '展开子目录'}
            className="p-0.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground"
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

        {/* 节点图标 */}
        {hasChildren ? (
          isExpanded ? (
            <FolderOpen className="w-4 h-4 text-primary shrink-0" />
          ) : (
            <Folder className="w-4 h-4 text-primary shrink-0" />
          )
        ) : isHit ? (
          <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
        ) : isPruned ? (
          <Scissors className="w-4 h-4 text-destructive shrink-0" />
        ) : (
          <FileText className="w-4 h-4 text-muted-foreground shrink-0" />
        )}

        {/* 节点名称与路径 */}
        <div className="flex-1 min-w-0 flex items-center gap-2">
          <span className={`font-medium truncate ${isHit ? 'font-semibold text-emerald-700 dark:text-emerald-300' : ''}`}>
            {node.name}
          </span>
          <span className="text-[10px] text-muted-foreground/70 font-mono truncate hidden sm:inline">
            {node.path}
          </span>
        </div>

        {/* 相似度得分与阈值标签 */}
        <div className="flex items-center gap-1.5 shrink-0">
          <span className="font-mono text-[11px] px-1.5 py-0.5 rounded bg-muted/60 border border-border">
            得分: {node.similarity_score.toFixed(3)}
          </span>

          {/* 剪枝/命中状态徽章 */}
          {isHit ? (
            <span className={`inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full font-medium border ${badgeColor}`}>
              <Sparkles className="w-3 h-3 text-emerald-500" />
              命中装配
            </span>
          ) : isPruned ? (
            <span
              title={node.reason_detail || pruningMeta.desc}
              className={`inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full font-medium border ${badgeColor}`}
            >
              <Scissors className="w-3 h-3" />
              {pruningMeta.label}
            </span>
          ) : null}
        </div>
      </div>

      {/* 剪枝原因描述（若被剪枝） */}
      {isPruned && node.reason_detail && (
        <div
          className="text-[10px] text-muted-foreground/90 pl-3 py-0.5 mb-1 italic flex items-center gap-1"
          style={{ marginLeft: `${node.depth * 18 + 24}px` }}
        >
          <HelpCircle className="w-3 h-3 text-muted-foreground/60 shrink-0" />
          <span>剪枝诱因: {node.reason_detail}</span>
        </div>
      )}

      {/* 递归渲染子节点 */}
      {hasChildren && isExpanded && (
        <div className="border-l border-border/40 ml-3 pl-0.5">
          {node.children.map((child) => (
            <TreeNodeItem
              key={child.node_id}
              node={child}
              isExpanded={expandedMap[child.node_id] ?? true}
              onToggle={onToggle}
              expandedMap={expandedMap}
            />
          ))}
        </div>
      )}
    </div>
  );
};

export const RetrievalDecisionTreeView: React.FC<RetrievalDecisionTreeViewProps> = ({
  nodes,
  className = '',
  defaultExpanded = true,
}) => {
  const [expandedMap, setExpandedMap] = useState<Record<string, boolean>>({});

  const toggleNode = (nodeId: string) => {
    setExpandedMap((prev) => ({
      ...prev,
      [nodeId]: !(prev[nodeId] ?? defaultExpanded),
    }));
  };

  if (!nodes || nodes.length === 0) {
    return (
      <div className={`p-6 text-center text-xs text-muted-foreground bg-muted/10 rounded-lg border border-dashed border-border ${className}`}>
        暂无检索下钻决策树记录
      </div>
    );
  }

  return (
    <div className={`space-y-1 overflow-x-auto ${className}`}>
      {nodes.map((node) => (
        <TreeNodeItem
          key={node.node_id}
          node={node}
          isExpanded={expandedMap[node.node_id] ?? defaultExpanded}
          onToggle={toggleNode}
          expandedMap={expandedMap}
        />
      ))}
    </div>
  );
};
