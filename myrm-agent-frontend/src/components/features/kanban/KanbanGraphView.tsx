/**
 * [INPUT]
 * - @xyflow/react (POS: 节点图渲染)
 * - @dagrejs/dagre (POS: 有向图分层布局)
 * - @/lib/utils/a11y::activateOnKey (POS: 非原生按钮的键盘激活)
 * - @/services/kanban::KanbanTask, TaskDependency, TaskStatus (POS: 看板 API 类型定义)
 *
 * [OUTPUT]
 * - KanbanGraphView (default): 任务依赖 DAG 视图（Dagre 自上而下布局，running 节点脉冲、failed 节点抖动，连线按父任务状态着色，小地图同色）
 *
 * [POS]
 * 看板「依赖图」标签页。节点点击回调给主视图打开详情抽屉；没有任务时显示空状态。
 */
'use client';

import { useCallback, useEffect, useMemo, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  useReactFlow,
  type Node,
  type Edge,
  type NodeProps,
  Handle,
  Position,
  MarkerType,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { GitBranch } from 'lucide-react';
import Dagre from '@dagrejs/dagre';
import type { KanbanTask, TaskStatus, TaskDependency } from '@/services/kanban';
import { activateOnKey } from '@/lib/utils/a11y';

const STATUS_NODE_COLORS: Record<TaskStatus, { bg: string; border: string }> = {
  triage: { bg: 'bg-purple-500/10', border: 'border-purple-500/40' },
  backlog: { bg: 'bg-muted/60', border: 'border-muted-foreground/30' },
  ready: { bg: 'bg-primary/10', border: 'border-primary/40' },
  running: { bg: 'bg-chart-4/15', border: 'border-chart-4/50' },
  blocked: { bg: 'bg-destructive/10', border: 'border-destructive/40' },
  in_review: { bg: 'bg-amber-500/10', border: 'border-amber-500/40' },
  completed: { bg: 'bg-chart-2/10', border: 'border-chart-2/40' },
  failed: { bg: 'bg-destructive/15', border: 'border-destructive/50' },
  archived: { bg: 'bg-muted/30', border: 'border-muted-foreground/20' },
};

// Opaque 600 shades for the finished/failed states: the theme's chart-2 is a pale green (about 1.7:1 on the
// card) and its dark-theme destructive is a dark red (about 2:1), too faint for a 1.5px dependency line.
const COMPLETED_COLOR = 'var(--color-emerald-600, #059669)';
const FAILED_COLOR = 'var(--color-red-600, #dc2626)';

const STATUS_MINIMAP_COLOR: Record<TaskStatus, string> = {
  triage: '#a855f7',
  backlog: '#888',
  ready: 'var(--primary)',
  running: 'var(--chart-4)',
  blocked: FAILED_COLOR,
  in_review: '#f59e0b',
  completed: COMPLETED_COLOR,
  failed: FAILED_COLOR,
  archived: '#666',
};

interface TaskNodeData {
  task: KanbanTask;
  onSelect?: (taskId: string) => void;
  [key: string]: unknown;
}

function TaskNode({ data }: NodeProps<Node<TaskNodeData>>) {
  const t = useTranslations('kanban');
  const { task, onSelect } = data;
  const colors = STATUS_NODE_COLORS[task.status] || STATUS_NODE_COLORS.backlog;
  const hasProgress = task.children_total > 0;
  const progressDone = hasProgress && task.children_done === task.children_total;

  return (
    <>
      <Handle type="target" position={Position.Top} className="!w-2 !h-2 !bg-muted-foreground/40" />
      <div
        data-testid={`kanban-graph-node-${task.task_id}`}
        className={cn(
          'rounded-lg border-2 px-3 py-2 min-w-[160px] max-w-[220px] cursor-pointer',
          'transition-shadow hover:shadow-md',
          colors.bg,
          colors.border,
          task.status === 'running' && 'animate-node-pulse',
          task.status === 'failed' && 'animate-shake',
        )}
        onClick={() => onSelect?.(task.task_id)}
        // oxlint-disable-next-line jsx-a11y/prefer-tag-over-role -- the card holds block-level progress and metadata rows, which cannot sit inside a native button
        role="button"
        tabIndex={0}
        onKeyDown={activateOnKey}
      >
        <div className="flex items-center gap-1.5 mb-1">
          <span
            className={cn(
              'w-2 h-2 rounded-full shrink-0',
              task.status === 'completed'
                ? 'bg-chart-2'
                : task.status === 'running'
                  ? 'bg-chart-4'
                  : task.status === 'failed' || task.status === 'blocked'
                    ? 'bg-destructive'
                    : task.status === 'ready'
                      ? 'bg-primary'
                      : task.status === 'triage'
                        ? 'bg-purple-500'
                        : 'bg-muted-foreground/50',
            )}
          />
          <span className="text-[10px] uppercase tracking-wider font-medium text-muted-foreground">
            {t(`status.${task.status}`)}
          </span>
          {typeof task.metadata?.branch === 'string' && (
            <span
              className="ml-auto inline-flex items-center text-[9px] px-1.5 py-0.5 rounded-full bg-blue-500/10 text-blue-500 border border-blue-500/20 truncate max-w-[80px]"
              title={String(task.metadata.branch)}
            >
              <GitBranch className="w-2.5 h-2.5 mr-0.5 shrink-0" />
              <span className="truncate">{String(task.metadata.branch)}</span>
            </span>
          )}
        </div>
        <p className="text-xs font-medium text-foreground truncate" title={task.title}>
          {task.title}
        </p>
        {hasProgress && (
          <div className="mt-1 flex items-center gap-1">
            <div className="flex-1 h-1 rounded-full bg-muted-foreground/20 overflow-hidden">
              <div
                className={cn('h-full rounded-full transition-all', progressDone ? 'bg-chart-2' : 'bg-primary')}
                style={{ width: `${(task.children_done / task.children_total) * 100}%` }}
              />
            </div>
            <span className={cn('text-[9px] font-medium', progressDone ? 'text-chart-2' : 'text-primary')}>
              {task.children_done}/{task.children_total}
            </span>
          </div>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} className="!w-2 !h-2 !bg-muted-foreground/40" />
    </>
  );
}

const nodeTypes = { task: TaskNode };

const EDGE_STATUS_STYLE: Partial<Record<TaskStatus, { stroke: string; strokeDasharray?: string }>> = {
  completed: { stroke: COMPLETED_COLOR },
  blocked: { stroke: FAILED_COLOR, strokeDasharray: '5 3' },
  failed: { stroke: FAILED_COLOR, strokeDasharray: '5 3' },
};

function layoutGraph(nodes: Node[], edges: Edge[], direction: 'TB' | 'LR' = 'TB') {
  const g = new Dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: direction, nodesep: 50, ranksep: 80 });

  for (const node of nodes) {
    g.setNode(node.id, { width: 200, height: 80 });
  }
  for (const edge of edges) {
    g.setEdge(edge.source, edge.target);
  }

  Dagre.layout(g);

  return nodes.map((node) => {
    const pos = g.node(node.id);
    return {
      ...node,
      position: { x: pos.x - 100, y: pos.y - 40 },
    };
  });
}

interface KanbanGraphViewProps {
  tasks: KanbanTask[];
  edges: TaskDependency[];
  onTaskSelect?: (taskId: string) => void;
}

function KanbanGraphViewInner({ tasks, edges: edgeData, onTaskSelect }: KanbanGraphViewProps) {
  const t = useTranslations('kanban');
  const { fitView } = useReactFlow();
  const prevNodeCountRef = useRef(tasks.length);

  const taskMap = useMemo(() => new Map(tasks.map((tk) => [tk.task_id, tk])), [tasks]);

  const { initialNodes, initialEdges } = useMemo(() => {
    const flowNodes: Node<TaskNodeData>[] = tasks.map((task) => ({
      id: task.task_id,
      type: 'task',
      position: { x: 0, y: 0 },
      data: { task, onSelect: onTaskSelect },
    }));

    const flowEdges: Edge[] = edgeData.map((dep) => {
      const parentStatus = taskMap.get(dep.parent_task_id)?.status;
      const statusStyle = parentStatus ? EDGE_STATUS_STYLE[parentStatus] : undefined;
      return {
        id: `${dep.parent_task_id}->${dep.child_task_id}`,
        source: dep.parent_task_id,
        target: dep.child_task_id,
        markerEnd: { type: MarkerType.ArrowClosed, width: 12, height: 12 },
        style: {
          strokeWidth: 1.5,
          ...statusStyle,
        },
        animated: parentStatus === 'running',
      };
    });

    const laid = layoutGraph(flowNodes, flowEdges);
    return { initialNodes: laid, initialEdges: flowEdges };
  }, [tasks, edgeData, onTaskSelect, taskMap]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [flowEdges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  useEffect(() => {
    setNodes(initialNodes);
    setEdges(initialEdges);

    if (tasks.length !== prevNodeCountRef.current) {
      prevNodeCountRef.current = tasks.length;
      requestAnimationFrame(() => fitView({ padding: 0.2, duration: 300 }));
    }
  }, [initialNodes, initialEdges, setNodes, setEdges, tasks.length, fitView]);

  const minimapNodeColor = useCallback((node: Node) => {
    const task = (node.data as TaskNodeData)?.task;
    if (!task) {
      return '#888';
    }
    return STATUS_MINIMAP_COLOR[task.status] || '#888';
  }, []);

  if (tasks.length === 0) {
    return (
      <div className="flex items-center justify-center h-[400px] text-sm text-muted-foreground">{t('noTasks')}</div>
    );
  }

  return (
    <div className="w-full h-[calc(100vh-280px)] min-h-[400px] rounded-lg border border-border/50 bg-background/50">
      <ReactFlow
        nodes={nodes}
        edges={flowEdges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.3}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={20} size={1} className="!bg-background" />
        <Controls
          showInteractive={false}
          className="!bg-muted !border-border !rounded-lg ! [&>button]:!bg-muted [&>button]:!border-border [&>button]:!text-foreground [&>button:hover]:!bg-accent"
        />
        <MiniMap
          nodeColor={minimapNodeColor}
          maskColor="color-mix(in srgb, var(--background) 70%, transparent)"
          className="!bg-muted/50 !border-border !rounded-lg"
          pannable
          zoomable
        />
      </ReactFlow>
    </div>
  );
}

export default function KanbanGraphView(props: KanbanGraphViewProps) {
  const t = useTranslations('kanban');
  if (props.tasks.length === 0) {
    return (
      <div className="flex items-center justify-center h-[400px] text-sm text-muted-foreground">{t('noTasks')}</div>
    );
  }
  return (
    <ReactFlowProvider>
      <KanbanGraphViewInner {...props} />
    </ReactFlowProvider>
  );
}
