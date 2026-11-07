'use client';

/**
 * [INPUT] ./knowledgeGraphModel (POS: 节点与关系的配色、节点显示名)
 * [OUTPUT] Legend: 关系类型图例与显隐开关；NodeDetail: 选中节点的详情卡片
 * [POS] MemoryKnowledgeGraph 的两个浮层面板，数据与回调全部由父组件传入，自身不持有状态。
 */

import { memo, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import {
  type ForceGraphData,
  type ForceNode,
  NODE_COLORS,
  REL_COLORS,
  REL_KEYS,
  getLinkColor,
  getNodeColor,
  getNodeDisplayName,
  nodeId,
} from './knowledgeGraphModel';

export const Legend = memo<{
  hiddenRelTypes: Set<string>;
  onToggle: (relType: string) => void;
  t: ReturnType<typeof useTranslations<'memory'>>;
}>(({ hiddenRelTypes, onToggle, t }) => (
  <div className="absolute bottom-3 left-3 z-10 flex max-w-[200px] flex-col gap-1.5 rounded-lg border border-border/60 bg-background/90 p-2.5 backdrop-blur-sm sm:max-w-none">
    <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">
      {t('commandCenter.graph.legend')}
    </span>
    <div className="flex items-center gap-3">
      <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
        <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: NODE_COLORS.Claim }} />
        Claim
      </span>
      <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
        <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: NODE_COLORS.Evidence }} />
        Evidence
      </span>
    </div>
    <div className="flex flex-wrap gap-x-3 gap-y-1">
      {REL_KEYS.map((rel) => (
        <button
          key={rel}
          type="button"
          onClick={() => onToggle(rel)}
          className={cn(
            'flex items-center gap-1 text-[11px] transition-opacity',
            hiddenRelTypes.has(rel) ? 'opacity-40 line-through' : 'opacity-100',
          )}
        >
          <span className="inline-block h-0.5 w-3 rounded-full" style={{ background: REL_COLORS[rel] }} />
          <span className="text-muted-foreground">{t(`commandCenter.graph.relType.${rel}`)}</span>
        </button>
      ))}
    </div>
  </div>
));
Legend.displayName = 'Legend';

export const NodeDetail = memo<{
  node: ForceNode;
  data: ForceGraphData;
  onClose: () => void;
  t: ReturnType<typeof useTranslations<'memory'>>;
}>(({ node, data, onClose, t }) => {
  const connections = useMemo(() => {
    return data.links.filter((l) => nodeId(l.source) === node.id || nodeId(l.target) === node.id);
  }, [data.links, node.id]);

  return (
    <div className="absolute bottom-3 right-3 z-10 w-64 max-h-72 overflow-y-auto rounded-lg border border-border/60 bg-background/95 p-3 backdrop-blur-sm sm:w-72">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <span
              className={cn(
                'inline-block h-2.5 w-2.5 shrink-0',
                node.labels.includes('Evidence') ? 'rounded-sm' : 'rounded-full',
              )}
              style={{ background: getNodeColor(node.labels) }}
            />
            <span className="truncate text-xs font-semibold text-foreground">{node.labels.join(', ')}</span>
          </div>
          <p className="mt-1 line-clamp-3 text-[11px] leading-4 text-muted-foreground">{getNodeDisplayName(node)}</p>
        </div>
        <button type="button" onClick={onClose} className="shrink-0">
          <X className="h-3.5 w-3.5 text-muted-foreground" />
        </button>
      </div>
      {connections.length > 0 && (
        <div className="mt-2 space-y-1 border-t border-border/40 pt-2">
          <span className="text-[10px] font-medium text-muted-foreground">
            {t('commandCenter.graph.connections', { count: connections.length })}
          </span>
          {connections.slice(0, 10).map((l) => {
            const peer = nodeId(l.source) === node.id ? nodeId(l.target) : nodeId(l.source);
            const direction = nodeId(l.source) === node.id ? '→' : '←';
            return (
              <div key={l.id} className="flex items-center gap-1.5 text-[11px]">
                <span
                  className="inline-block h-0.5 w-2.5 rounded-full"
                  style={{ background: getLinkColor(l.rel_type) }}
                />
                <span className="text-muted-foreground">{l.rel_type}</span>
                <span className="text-muted-foreground/60">{direction}</span>
                <span className="truncate text-foreground/80">{peer.slice(0, 12)}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
});
NodeDetail.displayName = 'NodeDetail';
