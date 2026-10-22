import React, { useState, useCallback, useMemo } from 'react';
import { Network, Activity, Send, Database, GitFork, RefreshCw, X } from 'lucide-react';

export type SwarmTopologyType = 'star' | 'hierarchical_tree' | 'peer_mesh' | 'pipeline' | 'ring';
export type SwarmNodeRole = 'coordinator' | 'worker' | 'reviewer' | 'specialist' | 'gateway';
export type SwarmNodeStatus = 'idle' | 'active' | 'busy' | 'migrating' | 'degraded' | 'offline';
export type MessageRoutingMode = 'unicast' | 'multicast' | 'broadcast';

export interface SwarmNodeData {
  node_id: string;
  name: string;
  role: SwarmNodeRole;
  status: SwarmNodeStatus;
  capabilities: string[];
  connected_peers: string[];
  workload_score: number;
  meta: Record<string, string>;
}

export interface MeshEdgeData {
  source: string;
  target: string;
  bidirectional: boolean;
  weight: number;
}

export interface MeshMessageData {
  message_id: string;
  sender_id: string;
  recipient_id: string;
  routing_mode: MessageRoutingMode;
  channel: string;
  payload: Record<string, string | number | boolean>;
  timestamp: number;
  delivery_status: string;
}

export interface BlackboardEntryData {
  key: string;
  value: string;
  author_id: string;
  version: number;
  updated_at: number;
  tags: string[];
}

export interface SwarmTopologyStateData {
  topology_id: string;
  topology_type: SwarmTopologyType;
  nodes: Record<string, SwarmNodeData>;
  edges: MeshEdgeData[];
  blackboard: Record<string, BlackboardEntryData>;
  recent_messages: MeshMessageData[];
  is_adaptive: boolean;
}

export interface SwarmTopologyMeshCardProps {
  chatId?: string;
  initialState?: SwarmTopologyStateData;
  onDismiss?: () => void;
  onTopologyChange?: (newType: SwarmTopologyType) => void;
}

const DEFAULT_NODES: Record<string, SwarmNodeData> = {
  'agent-coordinator-01': {
    node_id: 'agent-coordinator-01',
    name: 'Coordinator Orchestrator',
    role: 'coordinator',
    status: 'active',
    capabilities: ['task_decomposition', 'consensus_dispatch', 'handoff'],
    connected_peers: ['agent-worker-01', 'agent-worker-02', 'agent-reviewer-01'],
    workload_score: 0.25,
    meta: {},
  },
  'agent-worker-01': {
    node_id: 'agent-worker-01',
    name: 'Primary Engineer Worker',
    role: 'worker',
    status: 'active',
    capabilities: ['coding', 'debugging', 'unit_test'],
    connected_peers: ['agent-coordinator-01'],
    workload_score: 0.65,
    meta: {},
  },
  'agent-worker-02': {
    node_id: 'agent-worker-02',
    name: 'Research & Data Worker',
    role: 'worker',
    status: 'active',
    capabilities: ['data_extraction', 'web_search', 'synthesis'],
    connected_peers: ['agent-coordinator-01'],
    workload_score: 0.4,
    meta: {},
  },
  'agent-reviewer-01': {
    node_id: 'agent-reviewer-01',
    name: 'Security & QA Reviewer',
    role: 'reviewer',
    status: 'active',
    capabilities: ['lint_audit', 'code_review', 'security_verification'],
    connected_peers: ['agent-coordinator-01'],
    workload_score: 0.3,
    meta: {},
  },
};

const DEFAULT_EDGES: MeshEdgeData[] = [
  { source: 'agent-coordinator-01', target: 'agent-worker-01', bidirectional: true, weight: 1 },
  { source: 'agent-coordinator-01', target: 'agent-worker-02', bidirectional: true, weight: 1 },
  { source: 'agent-coordinator-01', target: 'agent-reviewer-01', bidirectional: true, weight: 1 },
];

export const SwarmTopologyMeshCard: React.FC<SwarmTopologyMeshCardProps> = ({
  initialState,
  onDismiss,
  onTopologyChange,
}) => {
  const [topologyType, setTopologyType] = useState<SwarmTopologyType>(
    initialState?.topology_type || 'star'
  );
  const [nodes, setNodes] = useState<Record<string, SwarmNodeData>>(
    initialState?.nodes || DEFAULT_NODES
  );
  const [edges, setEdges] = useState<MeshEdgeData[]>(initialState?.edges || DEFAULT_EDGES);
  const [messages, setMessages] = useState<MeshMessageData[]>(
    initialState?.recent_messages || []
  );
  const [blackboard, setBlackboard] = useState<Record<string, BlackboardEntryData>>(
    initialState?.blackboard || {
      'swarm.goal': {
        key: 'swarm.goal',
        value: 'Autonomous Full-Stack Pipeline Execution',
        author_id: 'agent-coordinator-01',
        version: 1,
        updated_at: Date.now(),
        tags: ['goal', 'consensus'],
      },
    }
  );

  const [broadcastInput, setBroadcastInput] = useState('');
  const [newFactKey, setNewFactKey] = useState('');
  const [newFactValue, setNewFactValue] = useState('');
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const computeEdgesForType = useCallback((type: SwarmTopologyType, currentNodes: Record<string, SwarmNodeData>): MeshEdgeData[] => {
    const ids = Object.keys(currentNodes);
    if (ids.length < 2) {
      return [];
    }
    const newEdges: MeshEdgeData[] = [];
    if (type === 'star') {
      const hub = ids.find((id) => currentNodes[id]?.role === 'coordinator') || ids[0];
      ids.forEach((id) => {
        if (id !== hub) {
          newEdges.push({ source: hub, target: id, bidirectional: true, weight: 1 });
        }
      });
    } else if (type === 'peer_mesh') {
      for (let i = 0; i < ids.length; i++) {
        for (let j = i + 1; j < ids.length; j++) {
          newEdges.push({ source: ids[i], target: ids[j], bidirectional: true, weight: 1 });
        }
      }
    } else if (type === 'pipeline') {
      for (let i = 0; i < ids.length - 1; i++) {
        newEdges.push({ source: ids[i], target: ids[i + 1], bidirectional: false, weight: 1 });
      }
    } else if (type === 'ring') {
      for (let i = 0; i < ids.length; i++) {
        const next = ids[(i + 1) % ids.length];
        newEdges.push({ source: ids[i], target: next, bidirectional: false, weight: 1 });
      }
    } else {
      // hierarchical_tree
      const root = ids.find((id) => currentNodes[id]?.role === 'coordinator') || ids[0];
      ids.forEach((id) => {
        if (id !== root) {
          newEdges.push({ source: root, target: id, bidirectional: true, weight: 1 });
        }
      });
    }
    return newEdges;
  }, []);

  const handleSwitchTopology = useCallback(
    (newType: SwarmTopologyType) => {
      setTopologyType(newType);
      const updatedEdges = computeEdgesForType(newType, nodes);
      setEdges(updatedEdges);
      onTopologyChange?.(newType);
      setStatusMessage(`Swarm topology switched to ${newType}.`);
    },
    [computeEdgesForType, nodes, onTopologyChange]
  );

  const handleSendBroadcast = useCallback(() => {
    if (!broadcastInput.trim()) {
      return;
    }
    const newMsg: MeshMessageData = {
      message_id: `msg-${Date.now()}`,
      sender_id: 'agent-coordinator-01',
      recipient_id: '*',
      routing_mode: 'broadcast',
      channel: 'general_swarm',
      payload: { text: broadcastInput.trim() },
      timestamp: Date.now(),
      delivery_status: 'delivered',
    };
    setMessages((prev) => [newMsg, ...prev].slice(0, 20));
    setBroadcastInput('');
    setStatusMessage('Broadcast message delivered to all mesh nodes.');
  }, [broadcastInput]);

  const handleAddFact = useCallback(() => {
    if (!newFactKey.trim() || !newFactValue.trim()) {
      return;
    }
    const key = newFactKey.trim();
    const existing = blackboard[key];
    const newEntry: BlackboardEntryData = {
      key,
      value: newFactValue.trim(),
      author_id: 'agent-coordinator-01',
      version: existing ? existing.version + 1 : 1,
      updated_at: Date.now(),
      tags: ['user_fact'],
    };
    setBlackboard((prev) => ({ ...prev, [key]: newEntry }));
    setNewFactKey('');
    setNewFactValue('');
    setStatusMessage(`Blackboard fact '${key}' updated (v${newEntry.version}).`);
  }, [blackboard, newFactKey, newFactValue]);

  const handleMigrateWorker = useCallback((nodeId: string) => {
    const targetNode = nodes[nodeId];
    if (!targetNode) {
      return;
    }
    const newRole: SwarmNodeRole = targetNode.role === 'worker' ? 'reviewer' : 'worker';
    const updatedNode: SwarmNodeData = {
      ...targetNode,
      role: newRole,
      status: 'active',
      meta: { ...targetNode.meta, migrated_at: new Date().toISOString() },
    };
    const updatedNodes = { ...nodes, [nodeId]: updatedNode };
    setNodes(updatedNodes);
    setEdges(computeEdgesForType(topologyType, updatedNodes));
    setStatusMessage(`Node ${nodeId} migrated to ${newRole}.`);
  }, [computeEdgesForType, nodes, topologyType]);

  const nodeList = useMemo(() => Object.values(nodes), [nodes]);
  const blackboardList = useMemo(() => Object.values(blackboard), [blackboard]);

  return (
    <div
      data-testid="swarm-topology-mesh-card"
      className="my-3 rounded-xl border border-indigo-500/30 bg-slate-900/95 p-4 text-slate-100 shadow-xl backdrop-blur-md"
    >
      <div className="flex items-center justify-between border-b border-slate-700/60 pb-3">
        <div className="flex items-center gap-2">
          <div className="rounded-lg bg-indigo-500/20 p-1.5 text-indigo-400">
            <Network className="h-5 w-5" />
          </div>
          <div>
            <h3 className="font-semibold text-slate-100 flex items-center gap-2">
              SwarmForge Dynamic Topology & Mesh
              <span className="rounded bg-indigo-500/20 px-2 py-0.5 text-xs font-medium text-indigo-300 uppercase">
                {topologyType}
              </span>
            </h3>
            <p className="text-xs text-slate-400">
              P2P Agent Mesh Bus, Shared Blackboard & Live Migration
            </p>
          </div>
        </div>
        {onDismiss && (
          <button
            onClick={onDismiss}
            aria-label="Dismiss dialog"
            className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {statusMessage && (
        <div
          data-testid="status-banner"
          className="my-2 rounded bg-indigo-950/50 border border-indigo-800/40 px-3 py-1.5 text-xs text-indigo-300 flex items-center gap-1.5"
        >
          <Activity className="h-3.5 w-3.5 text-indigo-400" />
          <span>{statusMessage}</span>
        </div>
      )}

      {/* Metrics Header */}
      <div className="my-3 grid grid-cols-4 gap-2 text-center text-xs">
        <div className="rounded-lg bg-slate-800/60 p-2 border border-slate-700/40">
          <span className="text-slate-400">Active Nodes</span>
          <div data-testid="stat-nodes-count" className="text-base font-bold text-slate-100">
            {nodeList.length}
          </div>
        </div>
        <div className="rounded-lg bg-slate-800/60 p-2 border border-slate-700/40">
          <span className="text-slate-400">Mesh Edges</span>
          <div data-testid="stat-edges-count" className="text-base font-bold text-indigo-400">
            {edges.length}
          </div>
        </div>
        <div className="rounded-lg bg-slate-800/60 p-2 border border-slate-700/40">
          <span className="text-slate-400">Blackboard Facts</span>
          <div data-testid="stat-facts-count" className="text-base font-bold text-amber-400">
            {blackboardList.length}
          </div>
        </div>
        <div className="rounded-lg bg-slate-800/60 p-2 border border-slate-700/40">
          <span className="text-slate-400">Bus Messages</span>
          <div data-testid="stat-messages-count" className="text-base font-bold text-emerald-400">
            {messages.length}
          </div>
        </div>
      </div>

      {/* Topology Type Switcher */}
      <div className="mb-3">
        <span className="text-xs font-medium text-slate-300 block mb-1">
          Switch Swarm Topology Layout:
        </span>
        <div className="flex flex-wrap gap-1.5">
          {(['star', 'hierarchical_tree', 'peer_mesh', 'pipeline', 'ring'] as SwarmTopologyType[]).map(
            (type) => (
              <button
                key={type}
                data-testid={`btn-switch-${type}`}
                onClick={() => handleSwitchTopology(type)}
                className={`rounded px-2.5 py-1 text-xs font-medium transition-colors ${
                  topologyType === type
                    ? 'bg-indigo-600 text-white shadow'
                    : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
                }`}
              >
                {type}
              </button>
            )
          )}
        </div>
      </div>

      {/* Nodes & Edges Section */}
      <div className="mb-3 rounded-lg border border-slate-800 bg-slate-950/50 p-2.5">
        <div className="text-xs font-semibold text-slate-300 mb-2 flex items-center justify-between">
          <span>Active Mesh Nodes</span>
          <span className="text-slate-500 text-[10px]">Click node to trigger Live Migration</span>
        </div>
        <div className="grid grid-cols-2 gap-2">
          {nodeList.map((node) => (
            <div
              key={node.node_id}
              data-testid={`node-card-${node.node_id}`}
              className="flex items-center justify-between rounded border border-slate-700/60 bg-slate-800/60 p-2 text-xs"
            >
              <div className="truncate pr-1">
                <div className="font-medium text-slate-200 truncate">{node.name}</div>
                <div className="text-[10px] text-slate-400 flex items-center gap-1.5 mt-0.5">
                  <span className="rounded bg-indigo-900/60 px-1 py-0.2 text-indigo-300">
                    {node.role}
                  </span>
                  <span>peers: {node.connected_peers.length}</span>
                </div>
              </div>
              <button
                data-testid={`btn-migrate-${node.node_id}`}
                onClick={() => handleMigrateWorker(node.node_id)}
                title="Trigger Live Role Migration"
                className="shrink-0 rounded p-1 text-slate-400 hover:bg-indigo-600/40 hover:text-indigo-200 transition-colors"
              >
                <GitFork className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Mesh Bus Broadcast Form */}
      <div className="mb-3 rounded-lg border border-slate-800 bg-slate-950/50 p-2.5">
        <label htmlFor="input-broadcast-text" className="text-xs font-semibold text-slate-300 block mb-1.5 flex items-center gap-1.5">
          <Send className="h-3.5 w-3.5 text-indigo-400" />
          P2P Mesh Bus Broadcast:
        </label>
        <div className="flex gap-2">
          <input
            id="input-broadcast-text"
            data-testid="input-broadcast-text"
            type="text"
            value={broadcastInput}
            onChange={(e) => setBroadcastInput(e.target.value)}
            placeholder="Broadcast a directive to all mesh nodes..."
            className="flex-1 rounded border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
          />
          <button
            data-testid="btn-send-broadcast"
            onClick={handleSendBroadcast}
            disabled={!broadcastInput.trim()}
            className="rounded bg-indigo-600 px-3 py-1 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            Broadcast
          </button>
        </div>
      </div>

      {/* Shared Blackboard Facts */}
      <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-2.5">
        <div className="flex items-center justify-between text-xs font-semibold text-slate-300 mb-1.5">
          <span className="flex items-center gap-1.5">
            <Database className="h-3.5 w-3.5 text-amber-400" />
            Shared Blackboard Facts:
          </span>
        </div>
        <div className="space-y-1 mb-2 max-h-24 overflow-y-auto">
          {blackboardList.map((fact) => (
            <div
              key={fact.key}
              data-testid={`blackboard-fact-${fact.key}`}
              className="flex items-center justify-between rounded bg-slate-800/40 px-2 py-1 text-[11px]"
            >
              <span className="font-mono text-indigo-300">{fact.key}</span>
              <span className="text-slate-300 truncate max-w-[180px]">{fact.value}</span>
              <span className="text-[10px] text-amber-400">v{fact.version}</span>
            </div>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            data-testid="input-fact-key"
            type="text"
            value={newFactKey}
            onChange={(e) => setNewFactKey(e.target.value)}
            placeholder="Key (e.g., status.build)"
            className="w-1/3 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
          />
          <input
            data-testid="input-fact-value"
            type="text"
            value={newFactValue}
            onChange={(e) => setNewFactValue(e.target.value)}
            placeholder="Value..."
            className="flex-1 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
          />
          <button
            data-testid="btn-add-fact"
            onClick={handleAddFact}
            disabled={!newFactKey.trim() || !newFactValue.trim()}
            className="rounded bg-amber-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-amber-500 disabled:opacity-50"
          >
            Set Fact
          </button>
        </div>
      </div>
    </div>
  );
};
