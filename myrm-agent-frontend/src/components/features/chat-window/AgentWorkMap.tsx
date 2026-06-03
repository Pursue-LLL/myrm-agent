import React, { useMemo, useCallback, useEffect } from 'react';
import {
  ReactFlow,
  MiniMap,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  Handle,
  Position,
  Node,
  Edge,
  MarkerType,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import dagre from '@dagrejs/dagre';
import { useSubagentStore } from '@/store/chat/useSubagentStore';
import useChatStore from '@/store/useChatStore';
import { Bot, CheckCircle2, CircleDashed, Loader2, XCircle, AlertCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Badge } from '@/components/primitives/badge';
import { Card } from '@/components/primitives/card';

const dagreGraph = new dagre.graphlib.Graph();
dagreGraph.setDefaultEdgeLabel(() => ({}));

const nodeWidth = 280;
const nodeHeight = 120;

const getLayoutedElements = (nodes: Node[], edges: Edge[], direction = 'TB') => {
  const isHorizontal = direction === 'LR';
  dagreGraph.setGraph({ rankdir: direction });

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: nodeWidth, height: nodeHeight });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  const layoutedNodes = nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    const newNode = {
      ...node,
      targetPosition: isHorizontal ? Position.Left : Position.Top,
      sourcePosition: isHorizontal ? Position.Right : Position.Bottom,
      position: {
        x: nodeWithPosition.x - nodeWidth / 2,
        y: nodeWithPosition.y - nodeHeight / 2,
      },
    };
    return newNode;
  });

  return { nodes: layoutedNodes, edges };
};

const CustomNode = ({ data }: { data: any }) => {
  const { objective, status, agent_type, cost_usd, error } = data;

  const StatusIcon = {
    pending: CircleDashed,
    running: Loader2,
    completed: CheckCircle2,
    failed: XCircle,
    paused: AlertCircle,
  }[status as string] || CircleDashed;

  const statusColor = {
    pending: 'text-muted-foreground',
    running: 'text-blue-500 animate-spin',
    completed: 'text-green-500',
    failed: 'text-red-500',
    paused: 'text-yellow-500',
  }[status as string] || 'text-muted-foreground';

  const borderColor = {
    pending: 'border-border',
    running: 'border-blue-500',
    completed: 'border-green-500',
    failed: 'border-red-500',
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
};

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