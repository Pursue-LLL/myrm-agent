import React, { useEffect } from 'react';
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
  MarkerType,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import dagre from '@dagrejs/dagre';
import { useSubagentStore, type FissionTopologyNode } from '@/store/chat/useSubagentStore';
import useChatStore from '@/store/useChatStore';
import { Bot, CheckCircle2, CircleDashed, Loader2, XCircle, AlertCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Badge } from '@/components/primitives/badge';
import { Card } from '@/components/primitives/card';

const NODE_WIDTH = 280;
const NODE_HEIGHT = 120;

function getLayoutedElements(nodes: Node[], edges: Edge[], direction = 'TB') {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: direction });
  const isHorizontal = direction === 'LR';

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
      targetPosition: isHorizontal ? Position.Left : Position.Top,
      sourcePosition: isHorizontal ? Position.Right : Position.Bottom,
      position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 },
    };
  });

  return { nodes: layoutedNodes, edges };
}

interface SubagentNodeData extends FissionTopologyNode {
  [key: string]: unknown;
}

function CustomNode({ data }: NodeProps<Node<SubagentNodeData>>) {
  const { objective, status, agent_type, cost_usd, error } = data;

  const StatusIcon = {
    pending: CircleDashed,
    running: Loader2,
    verifying: Loader2,
    completed: CheckCircle2,
    failed: XCircle,
    timed_out: XCircle,
    cancelled: XCircle,
    cancelled_by_budget: XCircle,
    pending_approval: AlertCircle,
    yielded: CircleDashed,
    interrupted: AlertCircle,
    checkpoint: CircleDashed,
    paused: AlertCircle,
  }[status as string] || CircleDashed;

  const statusColor = {
    pending: 'text-muted-foreground',
    running: 'text-blue-500 animate-spin',
    verifying: 'text-purple-500 animate-spin',
    completed: 'text-green-500',
    failed: 'text-red-500',
    timed_out: 'text-orange-500',
    cancelled: 'text-muted-foreground',
    cancelled_by_budget: 'text-orange-500',
    pending_approval: 'text-yellow-500',
    yielded: 'text-muted-foreground',
    interrupted: 'text-orange-500',
    checkpoint: 'text-muted-foreground',
    paused: 'text-yellow-500',
  }[status as string] || 'text-muted-foreground';

  const borderColor = {
    pending: 'border-border',
    running: 'border-blue-500',
    verifying: 'border-purple-500',
    completed: 'border-green-500',
    failed: 'border-red-500',
    timed_out: 'border-orange-500',
    cancelled: 'border-border',
    cancelled_by_budget: 'border-orange-500',
    pending_approval: 'border-yellow-500',
    yielded: 'border-border',
    interrupted: 'border-orange-500',
    checkpoint: 'border-border',
    paused: 'border-yellow-500',
  }[status as string] || 'border-border';

  return (
    <Card className={cn("w-[280px] p-4 shadow-md bg-background flex flex-col gap-3", borderColor)}>
      <Handle type="target" position={Position.Top} className="w-2 h-2" />
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Bot className="w-4 h-4 text-muted-foreground" />
          <span className="font-semibold text-sm truncate">{agent_type}</span>
        </div>
        <StatusIcon className={cn("w-4 h-4", statusColor)} />
      </div>
      <p className="text-xs text-muted-foreground line-clamp-2" title={objective}>
        {objective}
      </p>
      <div className="flex items-center justify-between mt-auto">
        <Badge variant="outline" className="text-[10px]">
          {status}
        </Badge>
        {cost_usd !== undefined && cost_usd > 0 && (
          <span className="text-[10px] text-muted-foreground">${cost_usd.toFixed(4)}</span>
        )}
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

const nodeTypes = {
  custom: CustomNode,
};

export const AgentWorkMap = () => {
  const fissionTopology = useSubagentStore((state) => state.fissionTopology);
  const setFissionTopology = useSubagentStore((state) => state.setFissionTopology);
  const chatId = useChatStore((state) => state.chatId);

  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  // Fetch initial topology on mount
  useEffect(() => {
    if (chatId) {
      import('@/services/chat').then(({ getFissionTopology }) => {
        getFissionTopology(chatId).then((topology) => {
          if (topology) {
            setFissionTopology({
              fission_id: topology.fission_id,
              nodes: topology.nodes,
              total_cost_usd: topology.total_cost_usd,
            });
          }
        });
      });
    }
  }, [chatId, setFissionTopology]);

  useEffect(() => {
    if (!fissionTopology) {
      setNodes([]);
      setEdges([]);
      return;
    }

    const initialNodes: Node[] = [
      {
        id: 'root',
        type: 'default',
        data: { label: `Fission Batch: ${fissionTopology.fission_id.slice(0, 8)}...` },
        position: { x: 0, y: 0 },
        className: 'font-semibold !bg-primary/10 !border-primary text-primary shadow-sm rounded-lg',
      },
    ];

    const initialEdges: Edge[] = [];

    fissionTopology.nodes.forEach((node) => {
      initialNodes.push({
        id: node.node_id,
        type: 'custom',
        data: { ...node },
        position: { x: 0, y: 0 },
      });

      initialEdges.push({
        id: `edge-root-${node.node_id}`,
        source: 'root',
        target: node.node_id,
        type: 'smoothstep',
        animated: node.status === 'running',
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: 'currentColor',
        },
        style: { stroke: 'currentColor', opacity: 0.5 },
      });
    });

    const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(
      initialNodes,
      initialEdges
    );

    setNodes(layoutedNodes);
    setEdges(layoutedEdges);
  }, [fissionTopology, setNodes, setEdges]);

  if (!fissionTopology) return null;

  return (
    <div className="w-full h-[400px] border rounded-lg overflow-hidden bg-dot-pattern bg-background relative my-4">
      <div className="absolute top-4 left-4 z-10 bg-background/80 backdrop-blur-sm p-2 rounded-md border shadow-sm flex flex-col gap-1 pointer-events-none">
        <h3 className="font-semibold text-sm">Agent Work Map</h3>
        <p className="text-xs text-muted-foreground">
          Total Cost: <span className="font-mono">${fissionTopology.total_cost_usd.toFixed(4)}</span>
        </p>
      </div>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        fitView
        attributionPosition="bottom-right"
      >
        <Controls />
        <MiniMap zoomable pannable nodeClassName="bg-primary/20" />
        <Background gap={12} size={1} />
      </ReactFlow>
    </div>
  );
};

export default AgentWorkMap;