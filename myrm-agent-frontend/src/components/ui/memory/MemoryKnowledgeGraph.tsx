'use client';

/**
 * [INPUT]
 * @/services/memoryCommandCenter::getMemoryGraph, MemoryCommandGraphResponse (POS: Frontend Personal Brain Command Center client)
 *
 * [OUTPUT]
 * MemoryKnowledgeGraph: Claim graph 2D force-directed visualization with relation coloring, search, legend, focus mode, and fullscreen.
 *
 * [POS]
 * 知识图谱可视化面板。以力导向 2D 图展示 Claim/Evidence 节点及 4 种语义关系，支持搜索过滤、关系类型筛选、节点聚焦、全屏模式与图例。
 */

import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import { useTranslations } from 'next-intl';
import { Maximize2, Minimize2, Search, X } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import {
  getMemoryGraph,
  type MemoryCommandGraphNode,
  type MemoryCommandGraphResponse,
  type MemoryCommandGraphStats,
} from '@/services/memoryCommandCenter';

const ForceGraph2D = dynamic(() => import('react-force-graph-2d'), { ssr: false });

const useCanvasLabelColor = () => {
  const [isDark, setIsDark] = useState(true);
  useEffect(() => {
    const update = () => setIsDark(document.documentElement.classList.contains('dark'));
    update();
    const mo = new MutationObserver(update);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    return () => mo.disconnect();
  }, []);
  return {
    fg: isDark ? 'rgba(251,251,248,0.9)' : 'rgba(10,10,10,0.85)',
    fgDim: isDark ? 'rgba(251,251,248,0.25)' : 'rgba(10,10,10,0.2)',
  };
};

interface ForceNode extends MemoryCommandGraphNode {
  x?: number;
  y?: number;
  __indexColor?: string;
}

interface ForceLink {
  source: string | ForceNode;
  target: string | ForceNode;
  rel_type: string;
  id: string;
  properties: Record<string, string | number>;
}

interface ForceGraphData {
  nodes: ForceNode[];
  links: ForceLink[];
}

const REL_COLORS: Record<string, string> = {
  SUPPORTED_BY: '#10b981',
  CONTRADICTED_BY: '#ef4444',
  SUPERSEDED_BY: '#f59e0b',
  CONSTRAINED_BY: '#3b82f6',
};
const REL_KEYS = Object.keys(REL_COLORS);
const DEFAULT_LINK_COLOR = '#6b7280';

const NODE_COLORS: Record<string, string> = {
  Claim: '#8b5cf6',
  Evidence: '#64748b',
};
const DEFAULT_NODE_COLOR = '#a1a1aa';

const getNodeColor = (labels: string[]): string =>
  labels.includes('Claim')
    ? NODE_COLORS.Claim
    : labels.includes('Evidence')
      ? NODE_COLORS.Evidence
      : DEFAULT_NODE_COLOR;

const getLinkColor = (relType: string): string => REL_COLORS[relType] ?? DEFAULT_LINK_COLOR;

const getNodeRadius = (labels: string[]): number => (labels.includes('Claim') ? 6 : 4);

const nodeId = (n: string | ForceNode): string => (typeof n === 'string' ? n : n.id);

const toForceGraph = (resp: MemoryCommandGraphResponse): ForceGraphData => ({
  nodes: resp.nodes.map((n) => ({ ...n })),
  links: resp.edges.map((e) => ({
    source: e.source,
    target: e.target,
    rel_type: e.rel_type,
    id: e.id,
    properties: e.properties,
  })),
});

const getNodeDisplayName = (node: ForceNode): string => {
  const props = node.properties;
  if (typeof props.content === 'string' && props.content.length > 0) {
    return props.content.length > 60 ? `${props.content.slice(0, 57)}…` : props.content;
  }
  if (typeof props.name === 'string') return props.name;
  return node.labels[0] ?? node.id.slice(0, 8);
};

const MemoryKnowledgeGraph = memo<{ className?: string }>(({ className }) => {
  const t = useTranslations('memory');
  const themeColors = useCanvasLabelColor();
  const containerRef = useRef<HTMLDivElement>(null);
  const [data, setData] = useState<ForceGraphData | null>(null);
  const [stats, setStats] = useState<MemoryCommandGraphStats | null>(null);
  const [hasGraph, setHasGraph] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dimensions, setDimensions] = useState({ width: 600, height: 400 });
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedNode, setSelectedNode] = useState<ForceNode | null>(null);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [fullscreen, setFullscreen] = useState(false);
  const [hiddenRelTypes, setHiddenRelTypes] = useState<Set<string>>(new Set());

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await getMemoryGraph(200, 0);
      setHasGraph(resp.has_graph);
      setStats(resp.stats);
      if (resp.has_graph && resp.nodes.length > 0) {
        setData(toForceGraph(resp));
      } else {
        setData(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!fullscreen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setFullscreen(false);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [fullscreen]);

  useEffect(() => {
    const container = fullscreen ? document.body : containerRef.current;
    if (!container) return;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) {
        setDimensions({
          width: entry.contentRect.width,
          height: fullscreen ? window.innerHeight : Math.max(entry.contentRect.height, 400),
        });
      }
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, [fullscreen]);

  const filteredData = useMemo<ForceGraphData | null>(() => {
    if (!data) return null;
    const q = searchQuery.toLowerCase().trim();
    const visibleNodes = q
      ? data.nodes.filter(
          (n) =>
            n.id.toLowerCase().includes(q) ||
            n.labels.some((l) => l.toLowerCase().includes(q)) ||
            getNodeDisplayName(n).toLowerCase().includes(q),
        )
      : data.nodes;
    const visibleIds = new Set(visibleNodes.map((n) => n.id));
    const visibleLinks = data.links.filter(
      (l) => !hiddenRelTypes.has(l.rel_type) && visibleIds.has(nodeId(l.source)) && visibleIds.has(nodeId(l.target)),
    );
    return { nodes: visibleNodes, links: visibleLinks };
  }, [data, searchQuery, hiddenRelTypes]);

  const neighbors = useMemo<Set<string>>(() => {
    if (!selectedNode || !data) return new Set();
    const set = new Set<string>();
    for (const l of data.links) {
      const src = nodeId(l.source);
      const tgt = nodeId(l.target);
      if (src === selectedNode.id) set.add(tgt);
      if (tgt === selectedNode.id) set.add(src);
    }
    return set;
  }, [selectedNode, data]);

  const nodeCanvasObject = useCallback(
    (node: ForceNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const x = node.x ?? 0;
      const y = node.y ?? 0;
      const r = getNodeRadius(node.labels);
      const color = getNodeColor(node.labels);
      const isFocused = selectedNode?.id === node.id;
      const isNeighbor = neighbors.has(node.id);
      const isHovered = hoveredNode === node.id;
      const dimmed = selectedNode && !isFocused && !isNeighbor;

      ctx.globalAlpha = dimmed ? 0.15 : 1;

      if (node.labels.includes('Evidence')) {
        ctx.fillStyle = color;
        ctx.fillRect(x - r, y - r, r * 2, r * 2);
        if (isFocused || isHovered) {
          ctx.strokeStyle = isFocused ? '#fff' : '#e2e8f0';
          ctx.lineWidth = 1.5 / globalScale;
          ctx.strokeRect(x - r, y - r, r * 2, r * 2);
        }
      } else {
        ctx.beginPath();
        ctx.arc(x, y, r, 0, 2 * Math.PI);
        ctx.fillStyle = color;
        ctx.fill();
        if (isFocused || isHovered) {
          ctx.strokeStyle = isFocused ? '#fff' : '#e2e8f0';
          ctx.lineWidth = 1.5 / globalScale;
          ctx.stroke();
        }
      }

      if (globalScale > 1.8 || isFocused) {
        const label = getNodeDisplayName(node);
        const fontSize = Math.min(12 / globalScale, 3.5);
        ctx.font = `${fontSize}px sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        ctx.fillStyle = dimmed ? themeColors.fgDim : themeColors.fg;
        ctx.fillText(label.slice(0, 24), x, y + r + 2);
      }
      ctx.globalAlpha = 1;
    },
    [selectedNode, neighbors, hoveredNode, themeColors],
  );

  const linkColor = useCallback(
    (link: ForceLink) => {
      const c = getLinkColor(link.rel_type);
      if (!selectedNode) return c;
      const src = nodeId(link.source);
      const tgt = nodeId(link.target);
      if (src === selectedNode.id || tgt === selectedNode.id) return c;
      return 'rgba(100,100,100,0.08)';
    },
    [selectedNode],
  );

  const toggleRelType = useCallback((relType: string) => {
    setHiddenRelTypes((prev) => {
      const next = new Set(prev);
      if (next.has(relType)) next.delete(relType);
      else next.add(relType);
      return next;
    });
  }, []);

  if (loading) {
    return (
      <div
        className={cn(
          'flex items-center justify-center rounded-lg border border-dashed border-border/70 p-12',
          className,
        )}
      >
        <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      </div>
    );
  }

  if (error) {
    return (
      <div className={cn('rounded-lg border border-destructive/20 bg-destructive/5 p-4', className)}>
        <p className="text-sm text-destructive">{error}</p>
        <button type="button" onClick={load} className="mt-2 rounded-lg border border-border px-3 py-1.5 text-xs">
          {t('commandCenter.graph.retry')}
        </button>
      </div>
    );
  }

  if (!hasGraph) {
    return (
      <div className={cn('rounded-lg border border-dashed border-border/70 p-8 text-center', className)}>
        <p className="text-sm text-muted-foreground">{t('commandCenter.graph.unavailable')}</p>
      </div>
    );
  }

  if (!data || data.nodes.length === 0) {
    return (
      <div className={cn('rounded-lg border border-dashed border-border/70 p-8 text-center', className)}>
        <p className="text-sm text-muted-foreground">{t('commandCenter.graph.empty')}</p>
      </div>
    );
  }

  const wrapperCls = fullscreen
    ? 'fixed inset-0 z-50 bg-background'
    : cn('relative rounded-lg border border-border/50 bg-accent/10 overflow-hidden', className);

  return (
    <div ref={containerRef} className={wrapperCls} style={fullscreen ? undefined : { minHeight: 400 }}>
      <div className="absolute left-3 top-3 z-10 flex items-center gap-2">
        <div className="flex items-center rounded-lg border border-border/60 bg-background/90 backdrop-blur-sm">
          <Search className="ml-2 h-3.5 w-3.5 text-muted-foreground" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t('commandCenter.graph.searchPlaceholder')}
            className="w-32 bg-transparent px-2 py-1.5 text-xs outline-none placeholder:text-muted-foreground/60 sm:w-44"
          />
          {searchQuery && (
            <button type="button" onClick={() => setSearchQuery('')} className="mr-1.5">
              <X className="h-3 w-3 text-muted-foreground" />
            </button>
          )}
        </div>
        <button
          type="button"
          onClick={() => setFullscreen((v) => !v)}
          className="rounded-lg border border-border/60 bg-background/90 p-1.5 backdrop-blur-sm"
        >
          {fullscreen ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
        </button>
      </div>

      {stats && (
        <div className="absolute right-3 top-3 z-10 flex gap-3 rounded-lg border border-border/60 bg-background/90 px-3 py-1.5 text-[11px] text-muted-foreground backdrop-blur-sm">
          <span>{t('commandCenter.graph.nodeCount', { count: stats.node_count })}</span>
          <span>{t('commandCenter.graph.edgeCount', { count: stats.relationship_count })}</span>
        </div>
      )}

      {filteredData && (
        <ForceGraph2D
          graphData={filteredData}
          width={dimensions.width}
          height={dimensions.height}
          nodeCanvasObject={nodeCanvasObject}
          nodePointerAreaPaint={(node: ForceNode, color: string, ctx: CanvasRenderingContext2D) => {
            const r = getNodeRadius(node.labels) + 2;
            ctx.fillStyle = color;
            ctx.beginPath();
            ctx.arc(node.x ?? 0, node.y ?? 0, r, 0, 2 * Math.PI);
            ctx.fill();
          }}
          linkColor={linkColor}
          linkWidth={(link: ForceLink) =>
            selectedNode && (nodeId(link.source) === selectedNode.id || nodeId(link.target) === selectedNode.id)
              ? 2
              : 0.8
          }
          linkDirectionalArrowLength={3}
          linkDirectionalArrowRelPos={1}
          backgroundColor="rgba(0,0,0,0)"
          onNodeClick={(node: ForceNode) => setSelectedNode((prev) => (prev?.id === node.id ? null : node))}
          onNodeHover={(node: ForceNode | null) => setHoveredNode(node?.id ?? null)}
          onBackgroundClick={() => setSelectedNode(null)}
        />
      )}

      <Legend hiddenRelTypes={hiddenRelTypes} onToggle={toggleRelType} t={t} />

      {selectedNode && <NodeDetail node={selectedNode} data={data} onClose={() => setSelectedNode(null)} t={t} />}
    </div>
  );
});

MemoryKnowledgeGraph.displayName = 'MemoryKnowledgeGraph';

const Legend = memo<{
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

const NodeDetail = memo<{
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

export default MemoryKnowledgeGraph;
