import React, { useEffect, useMemo, useRef } from 'react';
import {
  ReactFlow,
  MiniMap,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  Handle,
  Position,
  type Node,
  type Edge,
  type NodeProps,
  type ReactFlowInstance,
  MarkerType,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import dagre from '@dagrejs/dagre';
import { useSubagentStore, type SubagentNode } from '@/store/chat/useSubagentStore';
import {
  buildMergedTopologyModel,
  type TopologyModel,
  type TopologyNodeData,
  type TopologyTone,
} from '@/lib/utils/taskTopologyModel';
import { fmtCost, fmtTokens } from '@/lib/utils/subagentTree';
import { useTranslations } from 'next-intl';
import { Bot, CheckCircle2, CircleDashed, Loader2, XCircle, AlertCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Badge } from '@/components/primitives/badge';
import { Card } from '@/components/primitives/card';

const NODE_WIDTH = 280;
const NODE_HEIGHT = 130;

function getLayoutedElements<T extends Record<string, unknown>>(nodes: Node<T>[], edges: Edge[], direction = 'TB') {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: direction });

  for (const node of nodes) {
    g.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }
  for (const edge of edges) {
    g.setEdge(edge.source, edge.target);
  }

  dagre.layout(g);

  const layoutedNodes = nodes.map((node) => {
    const pos = g.node(node.id);
    return {
      ...node,
      targetPosition: Position.Top,
      sourcePosition: Position.Bottom,
      position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 },
    };
  });

  return { nodes: layoutedNodes, edges };
}

const STATUS_ICON: Record<string, { icon: typeof Loader2; className: string; spin?: boolean }> = {
  pending: { icon: CircleDashed, className: 'text-slate-400' },
  running: { icon: Loader2, className: 'text-blue-500', spin: true },
  verifying: { icon: Loader2, className: 'text-purple-500', spin: true },
  completed: { icon: CheckCircle2, className: 'text-green-500' },
  failed: { icon: XCircle, className: 'text-red-500' },
  timed_out: { icon: AlertCircle, className: 'text-orange-500' },
  cancelled: { icon: XCircle, className: 'text-muted-foreground' },
  cancelled_by_budget: { icon: XCircle, className: 'text-orange-500' },
  pending_approval: { icon: AlertCircle, className: 'text-yellow-500' },
  yielded: { icon: CircleDashed, className: 'text-muted-foreground' },
  interrupted: { icon: AlertCircle, className: 'text-orange-500' },
  checkpoint: { icon: CircleDashed, className: 'text-muted-foreground' },
};

const TONE_BORDER: Record<TopologyTone, string> = {
  active: 'border-blue-500',
  pending: 'border-yellow-400',
  success: 'border-green-500',
  danger: 'border-red-500',
  warning: 'border-purple-400',
  muted: 'border-border',
};

const TONE_PROGRESS_BAR: Record<TopologyTone, string> = {
  active: 'bg-blue-500',
  pending: 'bg-yellow-400',
  success: 'bg-green-500',
  danger: 'bg-red-500',
  warning: 'bg-purple-400',
  muted: 'bg-gray-400',
};

function formatDuration(totalSeconds: number): string {
  if (!Number.isFinite(totalSeconds) || totalSeconds <= 0) {
    return '';
  }
  if (totalSeconds < 60) {
    return `${Math.round(totalSeconds)}s`;
  }
  const min = Math.floor(totalSeconds / 60);
  const sec = Math.round(totalSeconds % 60);
  return `${min}m${sec}s`;
}

function CustomNode({ data }: NodeProps<Node<TopologyNodeData & Record<string, unknown>>>) {
  const t = useTranslations('subagentDashboard');
  const { label, agentType, status, tone, progress, costUsd, tokens, durationSeconds, error, isRoot, verification } =
    data;
  const config = STATUS_ICON[status] ?? { icon: CircleDashed, className: 'text-muted-foreground' };
  const StatusIcon = config.icon;
  const statusLabel = useMemo<Record<string, string>>(
    () => ({
      pending: t('statusLabel.pending'),
      running: t('statusLabel.running'),
      verifying: t('statusLabel.verifying'),
      completed: t('statusLabel.completed'),
      failed: t('statusLabel.failed'),
      timed_out: t('statusLabel.timed_out'),
      cancelled: t('statusLabel.cancelled'),
      cancelled_by_budget: t('statusLabel.cancelled_by_budget'),
      pending_approval: t('statusLabel.pending_approval'),
      yielded: t('statusLabel.yielded'),
      interrupted: t('statusLabel.interrupted'),
      checkpoint: t('statusLabel.checkpoint'),
    }),
    [t],
  );

  return (
    <Card
      className={cn('w-[240px] sm:w-[280px] p-3.5 shadow-md bg-background flex flex-col gap-2.5', TONE_BORDER[tone])}
    >
      <Handle type="target" position={Position.Top} className="w-2 h-2" />
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <Bot className={cn('w-4 h-4 shrink-0', isRoot ? 'text-primary' : 'text-muted-foreground')} />
          <span className="font-semibold text-sm truncate">{isRoot ? label : agentType}</span>
        </div>
        <StatusIcon className={cn('w-4 h-4 shrink-0', config.className, config.spin && 'animate-spin')} />
      </div>
      <p className="text-xs text-muted-foreground line-clamp-2" title={label}>
        {label}
      </p>
      {progress !== null && progress !== undefined && Number.isFinite(progress) && (
        <div className="flex items-center gap-1.5">
          <div className="flex-1 h-1.5 bg-muted/40 rounded-full overflow-hidden">
            <div
              className={cn('h-full rounded-full transition-all duration-500', TONE_PROGRESS_BAR[tone])}
              style={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
            />
          </div>
          <span className="text-[10px] text-muted-foreground tabular-nums">{Math.round(progress)}%</span>
        </div>
      )}
      <div className="flex items-center justify-between gap-2 mt-auto">
        <div className="flex items-center gap-1.5 min-w-0">
          {verification && !verification.passed && (
            <span className="inline-flex items-center gap-0.5 rounded-full bg-red-50 px-1.5 py-0.5 text-[10px] font-medium text-red-700 border border-red-200 dark:bg-red-900/30 dark:text-red-400 dark:border-red-800 shrink-0">
              <XCircle className="w-3 h-3" />
              {t('verificationFailed')}
            </span>
          )}
          <Badge variant="outline" className="text-[10px]">
            {statusLabel[status] ?? status}
          </Badge>
        </div>
        <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground tabular-nums">
          {costUsd > 0 && <span>{fmtCost(costUsd)}</span>}
          {tokens > 0 && <span>{fmtTokens(tokens)} tok</span>}
          {durationSeconds > 0 && <span>{formatDuration(durationSeconds)}</span>}
        </div>
      </div>
      {error && (
        <p className="text-[10px] text-red-500 line-clamp-1" title={error}>
          {error}
        </p>
      )}
      <Handle type="source" position={Position.Bottom} className="w-2 h-2" />
    </Card>
  );
}

const nodeTypes = { custom: CustomNode };

const TopologySummary = ({ model }: { model: TopologyModel }) => {
  const t = useTranslations('subagentDashboard');
  const parts: string[] = [`${model.nodes.length} ${t('agents')}`];
  if (model.activeCount > 0) {
    parts.push(`${model.activeCount} ${t('active')}`);
  }
  if (model.failedCount > 0) {
    parts.push(`${model.failedCount} ${t('failed')}`);
  }
  const cost = fmtCost(model.totalCostUsd);
  if (cost) {
    parts.push(cost);
  }
  if (model.totalTokens > 0) {
    parts.push(`${fmtTokens(model.totalTokens)} tok`);
  }
  const duration = formatDuration(model.totalDurationSeconds);
  if (duration) {
    parts.push(duration);
  }
  if (parts.length === 0) {
    return null;
  }
  return (
    <div className="px-4 pt-2 pb-1 text-[11px] text-muted-foreground border-b border-border/30">
      {parts.join(' · ')}
    </div>
  );
};

interface AgentWorkMapProps {
  chatId?: string;
  /** Called when a topology node is clicked, with the node task id. */
  onNodeClick?: (taskId: string) => void;
}

export const AgentWorkMap = ({ chatId: chatIdProp, onNodeClick }: AgentWorkMapProps) => {
  const t = useTranslations('subagentDashboard');
  const nodesMap = useSubagentStore((s) => s.nodes);
  const fissionTopology = useSubagentStore((s) => s.fissionTopology);
  const setFissionTopology = useSubagentStore((s) => s.setFissionTopology);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const rfRef = useRef<ReactFlowInstance | null>(null);

  const subagentNodes = useMemo<SubagentNode[]>(() => Object.values(nodesMap), [nodesMap]);

  const model = useMemo<TopologyModel>(
    () => buildMergedTopologyModel(subagentNodes, fissionTopology),
    [subagentNodes, fissionTopology],
  );

  // Fetch persisted fission topology once when the canvas mounts (Task Tray tab).
  useEffect(() => {
    if (!chatIdProp) {
      return;
    }
    import('@/services/chat').then(({ getFissionTopology }) => {
      getFissionTopology(chatIdProp).then((topology) => {
        if (topology) {
          setFissionTopology({
            fission_id: topology.fission_id,
            nodes: topology.nodes,
            total_cost_usd: topology.total_cost_usd,
          });
        }
      });
    });
  }, [chatIdProp, setFissionTopology]);

  const modelRef = useRef(model);
  modelRef.current = model;

  const nodeIdKey = useMemo(
    () =>
      model.nodes
        .map((n) => n.taskId)
        .sort()
        .join('|'),
    [model],
  );

  // Structure pass: dagre layout only when the node set changes (add/remove),
  // so user-dragged positions survive live data updates.
  useEffect(() => {
    const m = modelRef.current;
    if (m.nodes.length === 0) {
      setNodes([]);
      setEdges([]);
      return;
    }

    const idSet = new Set(m.nodes.map((n) => n.taskId));
    const initialNodes: Node<TopologyNodeData & Record<string, unknown>>[] = m.nodes.map((n) => ({
      id: n.taskId,
      type: 'custom',
      data: { ...n },
      position: { x: 0, y: 0 },
      className: n.isRoot ? '!bg-primary/10' : undefined,
    }));

    const initialEdges: Edge[] = m.edges
      .filter((e) => idSet.has(e.source) && idSet.has(e.target))
      .map((e) => {
        const target = m.nodes.find((n) => n.taskId === e.target);
        return {
          id: `edge-${e.source}-${e.target}`,
          source: e.source,
          target: e.target,
          type: 'smoothstep',
          animated: target?.tone === 'active',
          markerEnd: { type: MarkerType.ArrowClosed, color: 'currentColor' },
          style: { stroke: 'currentColor', opacity: 0.5 },
        };
      });

    const layout = getLayoutedElements(initialNodes, initialEdges);
    setNodes(layout.nodes);
    setEdges(layout.edges);
    // Follow the latest topology: after dagre relayout, newly added branches may
    // sit outside the current viewport, so refit the canvas to the whole graph.
    const raf = requestAnimationFrame(() => {
      rfRef.current?.fitView({ padding: 0.25, duration: 300, maxZoom: 1.2 });
    });
    return () => cancelAnimationFrame(raf);
  }, [nodeIdKey, setNodes, setEdges]);

  // Data pass: progress/status/meta updates refresh node data and edge animation
  // in place, keeping node coordinates stable.
  useEffect(() => {
    if (model.nodes.length === 0) {
      return;
    }
    const dataById = new Map(model.nodes.map((n) => [n.taskId, n]));
    setNodes((prev) =>
      prev.map((n) => {
        const d = dataById.get(n.id);
        return d ? { ...n, data: { ...d } } : n;
      }),
    );
    const activeIds = new Set(model.nodes.filter((n) => n.tone === 'active').map((n) => n.taskId));
    setEdges((prev) => prev.map((e) => ({ ...e, animated: activeIds.has(e.target) })));
  }, [model, setNodes, setEdges]);

  if (model.nodes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-[320px] gap-2 text-muted-foreground">
        <Bot className="w-8 h-8 opacity-40" />
        <p className="text-sm">{t('canvasEmpty')}</p>
        <p className="text-xs">{t('canvasEmptyHint')}</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-[440px]">
      <TopologySummary model={model} />
      <div className="flex-1 bg-background relative min-h-0 overflow-hidden">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          onInit={(instance) => {
            rfRef.current = instance;
          }}
          onNodeClick={(_, node) => onNodeClick?.(node.id)}
          fitView
          minZoom={0.2}
          attributionPosition="bottom-right"
        >
          <Controls />
          <MiniMap zoomable pannable nodeClassName="bg-primary/20" className="hidden sm:block" />
          <Background gap={12} size={1} />
        </ReactFlow>
      </div>
    </div>
  );
};

export default AgentWorkMap;
