'use client';

import React, { useEffect, useState, useRef, useCallback, useMemo } from 'react';
import dynamic from 'next/dynamic';
import { Loader2, RefreshCw, ChevronDown, ChevronUp, Eye, EyeOff } from 'lucide-react';
import { useTranslations } from 'next-intl';

const ForceGraph3D = dynamic(() => import('react-force-graph-3d'), { ssr: false });

interface GraphNode {
  id: string;
  name: string;
  group: number;
  val: number;
}

interface GraphLink {
  source: string | GraphNode;
  target: string | GraphNode;
  weight: number;
}

interface ApiResponse {
  nodes: GraphNode[];
  edges: GraphLink[];
}

interface ForceGraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

function apiToForceGraph(api: ApiResponse): ForceGraphData {
  return { nodes: api.nodes, links: api.edges };
}

function getLinkNodeId(node: string | GraphNode): string {
  return typeof node === 'string' ? node : node.id;
}

const GROUP_COLORS = [
  '#3b82f6', // blue-500
  '#10b981', // emerald-500
  '#f59e0b', // amber-500
  '#ef4444', // red-500
  '#8b5cf6', // violet-500
  '#ec4899', // pink-500
  '#06b6d4', // cyan-500
  '#84cc16', // lime-500
  '#f97316', // orange-500
  '#14b8a6', // teal-500
  '#6366f1', // indigo-500
  '#a855f7', // purple-500
  '#f43f5e', // rose-500
  '#0ea5e9', // sky-500
  '#22c55e', // green-500
  '#d946ef', // fuchsia-500
];

const getGroupColor = (group: number) => GROUP_COLORS[group % GROUP_COLORS.length];

export default function WikiGraph3D() {
  const t = useTranslations('library');
  const [data, setData] = useState<ForceGraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);

  // 交互式图例与过滤状态
  const [activeGroups, setActiveGroups] = useState<Set<number>>(new Set());
  const [isLegendCollapsed, setIsLegendCollapsed] = useState(false);

  // 提取所有唯一的 group
  const uniqueGroups = useMemo(() => {
    if (!data) return [];
    const groups = new Set<number>();
    data.nodes.forEach((n) => groups.add(n.group));
    return Array.from(groups).sort((a, b) => a - b);
  }, [data]);

  // 全选/全不选
  const toggleAllGroups = useCallback(() => {
    if (activeGroups.size === 0) {
      // 当前是全选状态（size===0代表不进行过滤，全显示），点击则全不选
      setActiveGroups(new Set(uniqueGroups));
    } else if (activeGroups.size === uniqueGroups.length) {
      // 当前是全不选状态，点击则恢复全选
      setActiveGroups(new Set());
    } else {
      // 部分选中，点击恢复全选
      setActiveGroups(new Set());
    }
  }, [activeGroups, uniqueGroups]);

  const toggleGroup = useCallback(
    (group: number) => {
      setActiveGroups((prev) => {
        const next = new Set(prev);
        // 如果当前是全选状态（size === 0），我们需要先将所有其他 group 加入 activeGroups
        if (prev.size === 0) {
          uniqueGroups.forEach((g) => {
            if (g !== group) next.add(g);
          });
        } else {
          if (next.has(group)) {
            next.delete(group);
          } else {
            next.add(group);
          }
        }

        // 如果全部都选中了，重置为 size === 0 以代表全选
        if (next.size === uniqueGroups.length) {
          return new Set();
        }
        return next;
      });
    },
    [uniqueGroups],
  );

  const isGroupActive = useCallback(
    (group: number) => {
      return activeGroups.size === 0 || activeGroups.has(group);
    },
    [activeGroups],
  );

  useEffect(() => {
    const fetchGraph = async () => {
      try {
        setLoading(true);
        setError(null);
        const response = await fetch('/api/v1/wiki/graph');

        if (!response.ok) {
          throw new Error('Failed to fetch graph data');
        }

        const result: ApiResponse = await response.json();
        setData(apiToForceGraph(result));
      } catch (err) {
        console.error('Error fetching Wiki graph:', err);
        setError(t('graph.error'));
        setData(null);
      } finally {
        setLoading(false);
      }
    };

    fetchGraph();
  }, [refreshTrigger]);

  const handleNodeClick = useCallback(async (node: GraphNode) => {
    try {
      const center = node.id || node.name;
      if (!center) return;

      const response = await fetch(`/api/v1/wiki/graph?center_node=${encodeURIComponent(center)}&depth=1&limit=50`);
      if (response.ok) {
        const newApi: ApiResponse = await response.json();
        const newData = apiToForceGraph(newApi);
        setData((prev) => {
          if (!prev) return newData;

          const nodeMap = new Map(prev.nodes.map((n) => [n.id, n]));
          newData.nodes.forEach((n) => nodeMap.set(n.id, n));

          const linkMap = new Map(
            prev.links.map((l) => {
              const s = getLinkNodeId(l.source);
              const tgt = getLinkNodeId(l.target);
              return [`${s}-${tgt}`, { ...l, source: s, target: tgt }];
            }),
          );

          newData.links.forEach((l) => {
            const s = getLinkNodeId(l.source);
            const tgt = getLinkNodeId(l.target);
            linkMap.set(`${s}-${tgt}`, { ...l, source: s, target: tgt });
          });

          return {
            nodes: Array.from(nodeMap.values()),
            links: Array.from(linkMap.values()),
          };
        });
      }
    } catch (err) {
      console.error('Failed to fetch neighborhood:', err);
    }
  }, []);

  useEffect(() => {
    const handleIdleStatus = (e: CustomEvent) => {
      const detail = e.detail;
      if (detail && detail.status === 'completed' && detail.task_name === 'wiki_maintenance') {
        setRefreshTrigger((prev) => prev + 1);
      }
    };

    window.addEventListener('idle-status', handleIdleStatus as EventListener);
    return () => window.removeEventListener('idle-status', handleIdleStatus as EventListener);
  }, []);

  useEffect(() => {
    const updateDimensions = () => {
      if (containerRef.current) {
        setDimensions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight || 600,
        });
      }
    };

    updateDimensions();
    window.addEventListener('resize', updateDimensions);
    return () => window.removeEventListener('resize', updateDimensions);
  }, []);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[50vh]">
        <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
        <p className="mt-4 text-sm text-muted-foreground">{t('graph.loading')}</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="w-full min-h-[600px] rounded-xl bg-black/5 flex flex-col items-center justify-center gap-4">
        <p className="text-destructive text-sm">{error}</p>
        <button
          onClick={() => setRefreshTrigger((prev) => prev + 1)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm hover:opacity-90 transition-opacity"
        >
          <RefreshCw size={16} />
          {t('graph.retry')}
        </button>
      </div>
    );
  }

  return (
    <div className="w-full h-full min-h-[600px] rounded-xl overflow-hidden bg-black/5 relative" ref={containerRef}>
      {data && data.nodes.length > 0 ? (
        <>
          <ForceGraph3D
            graphData={data}
            width={dimensions.width}
            height={dimensions.height}
            nodeLabel="name"
            nodeColor={(node: GraphNode) => getGroupColor(node.group)}
            nodeVisibility={(node: GraphNode) => isGroupActive(node.group)}
            linkVisibility={(link: GraphLink) => {
              const srcGroup =
                typeof link.source === 'object'
                  ? (link.source as GraphNode).group
                  : data.nodes.find((n) => n.id === link.source)?.group;
              const tgtGroup =
                typeof link.target === 'object'
                  ? (link.target as GraphNode).group
                  : data.nodes.find((n) => n.id === link.target)?.group;
              return (
                srcGroup !== undefined && tgtGroup !== undefined && isGroupActive(srcGroup) && isGroupActive(tgtGroup)
              );
            }}
            nodeVal="val"
            linkDirectionalArrowLength={3.5}
            linkDirectionalArrowRelPos={1}
            backgroundColor="rgba(0,0,0,0)"
            nodeRelSize={5}
            nodeOpacity={0.9}
            linkWidth={(link: GraphLink) => Math.max(0.5, (link.weight || 1) / 3)}
            linkColor={(link: GraphLink) => {
              if (!hoveredNode) return 'rgba(150, 150, 255, 0.4)';
              const src = typeof link.source === 'object' ? (link.source as unknown as GraphNode).id : link.source;
              const tgt = typeof link.target === 'object' ? (link.target as unknown as GraphNode).id : link.target;
              if (src === hoveredNode || tgt === hoveredNode) return 'rgba(100, 200, 255, 0.9)';
              return 'rgba(150, 150, 255, 0.1)';
            }}
            onNodeHover={(node: GraphNode | null) => setHoveredNode(node?.id || null)}
            onNodeClick={handleNodeClick}
          />

          {/* 交互式图例面板 */}
          {uniqueGroups.length > 0 && (
            <div className="absolute bottom-4 left-4 z-10 flex flex-col max-w-[220px] bg-background/80 dark:bg-background/80 border border-border rounded-xl shadow-lg backdrop-blur-md overflow-hidden transition-all duration-300">
              <div
                className="flex items-center justify-between w-full px-3 py-2 cursor-pointer bg-muted/50 hover:bg-muted/80 transition-colors"
                onClick={() => setIsLegendCollapsed(!isLegendCollapsed)}
              >
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold text-foreground">
                    {t('graph.legend', { defaultMessage: 'Node Types' })}
                  </span>
                  <span className="text-[10px] bg-primary/10 text-primary px-1.5 py-0.5 rounded-full">
                    {activeGroups.size === 0 ? uniqueGroups.length : activeGroups.size} / {uniqueGroups.length}
                  </span>
                </div>
                {isLegendCollapsed ? (
                  <ChevronUp size={14} className="text-muted-foreground" />
                ) : (
                  <ChevronDown size={14} className="text-muted-foreground" />
                )}
              </div>

              {!isLegendCollapsed && (
                <div className="flex flex-col p-2 space-y-1 max-h-[250px] overflow-y-auto scrollbar-hide">
                  <div
                    className="flex items-center justify-between px-2 py-1.5 rounded-lg cursor-pointer hover:bg-muted/50 text-xs text-muted-foreground mb-1"
                    onClick={toggleAllGroups}
                  >
                    <span>
                      {activeGroups.size === uniqueGroups.length
                        ? t('graph.selectAll', { defaultMessage: 'Select All' })
                        : t('graph.deselectAll', { defaultMessage: 'Toggle All' })}
                    </span>
                    {activeGroups.size === 0 ? <Eye size={12} /> : <EyeOff size={12} />}
                  </div>
                  {uniqueGroups.map((group) => {
                    const isActive = isGroupActive(group);
                    return (
                      <div
                        key={group}
                        onClick={() => toggleGroup(group)}
                        className={`flex items-center justify-between px-2 py-1.5 rounded-lg cursor-pointer transition-all duration-200 ${
                          isActive ? 'bg-transparent hover:bg-muted/50' : 'opacity-50 hover:opacity-80 bg-muted/30'
                        }`}
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <div
                            className="w-3 h-3 rounded-full flex-shrink-0"
                            style={{ backgroundColor: getGroupColor(group) }}
                          />
                          <span className="text-xs font-medium text-foreground truncate">Group {group}</span>
                        </div>
                        {!isActive && <EyeOff size={12} className="text-muted-foreground flex-shrink-0 ml-2" />}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </>
      ) : (
        <div className="flex flex-col items-center justify-center h-full">
          <p className="text-muted-foreground">{t('graph.empty')}</p>
        </div>
      )}
    </div>
  );
}
