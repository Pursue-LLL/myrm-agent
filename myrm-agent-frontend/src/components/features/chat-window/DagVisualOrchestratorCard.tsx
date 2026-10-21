import React, { useState, useId, useCallback } from 'react';
import {
  DagNodeItem,
  DagEdgeItem,
  DagNodeStatus,
  DEFAULT_DAG_NODES,
  DEFAULT_DAG_EDGES,
} from './dag-orchestrator/types';

interface DagVisualOrchestratorCardProps {
  chatId?: string;
  workflowId?: string;
  initialNodes?: Record<string, DagNodeItem>;
  initialEdges?: DagEdgeItem[];
  onColdResume?: (snapshotId: string) => void;
  onRejectLoopback?: (targetNodeId: string, feedback: string) => void;
}

const STATUS_COLOR_MAP: Record<DagNodeStatus, string> = {
  PENDING: 'bg-zinc-800 text-zinc-400 border-zinc-700',
  READY: 'bg-blue-950 text-blue-300 border-blue-700',
  RUNNING: 'bg-amber-950 text-amber-300 border-amber-700 animate-pulse',
  COMPLETED: 'bg-emerald-950 text-emerald-300 border-emerald-700',
  FAILED: 'bg-rose-950 text-rose-300 border-rose-700',
  SKIPPED: 'bg-zinc-900 text-zinc-500 border-zinc-800',
  REJECTED_LOOPBACK: 'bg-purple-950 text-purple-300 border-purple-700',
};

export const DagVisualOrchestratorCard: React.FC<DagVisualOrchestratorCardProps> = ({
  chatId = 'chat-default',
  workflowId = 'wf-dag-01',
  initialNodes = DEFAULT_DAG_NODES,
  initialEdges = DEFAULT_DAG_EDGES,
  onColdResume,
  onRejectLoopback,
}) => {
  const cardTitleId = useId();
  const [nodes, setNodes] = useState<Record<string, DagNodeItem>>(initialNodes);
  const [edges] = useState<DagEdgeItem[]>(initialEdges);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [showRejectForm, setShowRejectForm] = useState(false);
  const [rejectTargetId, setRejectTargetId] = useState<string>('code');
  const [rejectFeedback, setRejectFeedback] = useState<string>(
    'Architecture flaw identified in review: please refactor adapter layer',
  );
  const [notification, setNotification] = useState<string>('DAG orchestrator initialized and ready');
  const [isResuming, setIsResuming] = useState(false);

  const getDownstreamDependents = useCallback(
    (targetId: string): string[] => {
      const dependents: string[] = [];
      const queue: string[] = [targetId];
      const visited = new Set<string>();

      while (queue.length > 0) {
        const curr = queue.shift();
        if (!curr || visited.has(curr)) {
          continue;
        }
        visited.add(curr);

        for (const edge of edges) {
          if (edge.fromNode === curr && !visited.has(edge.toNode)) {
            dependents.push(edge.toNode);
            queue.push(edge.toNode);
          }
        }
      }
      return dependents;
    },
    [edges],
  );

  const handleColdResume = () => {
    setIsResuming(true);
    setNodes((prev) => {
      const next = { ...prev };
      for (const [id, node] of Object.entries(next)) {
        if (node.status === 'FAILED' || node.status === 'REJECTED_LOOPBACK') {
          next[id] = {
            ...node,
            status: 'READY',
            errorMessage: undefined,
            retryCount: node.retryCount + 1,
          };
        }
      }
      return next;
    });
    const msg = `Cold resume completed: restored from snapshot ${workflowId}-snap without re-executing completed nodes`;
    setNotification(msg);
    setIsResuming(false);
    onColdResume?.(`${workflowId}-snap`);
  };

  const handleExecuteRejectLoopback = (e: React.FormEvent) => {
    e.preventDefault();
    if (!rejectTargetId || !nodes[rejectTargetId]) {
      return;
    }

    const downstreamIds = getDownstreamDependents(rejectTargetId);

    setNodes((prev) => {
      const next = { ...prev };
      const targetNode = next[rejectTargetId];
      if (targetNode) {
        next[rejectTargetId] = {
          ...targetNode,
          status: 'REJECTED_LOOPBACK',
          feedbackHistory: [...targetNode.feedbackHistory, rejectFeedback],
        };
      }

      for (const downId of downstreamIds) {
        if (next[downId]) {
          next[downId] = {
            ...next[downId],
            status: 'PENDING',
            outputs: {},
            errorMessage: undefined,
          };
        }
      }
      return next;
    });

    const msg = `Cascade reject applied to node [${rejectTargetId}]: ${downstreamIds.length} downstream nodes cascaded to PENDING`;
    setNotification(msg);
    setShowRejectForm(false);
    onRejectLoopback?.(rejectTargetId, rejectFeedback);
  };

  const handleAdvanceStep = () => {
    setNodes((prev) => {
      const next = { ...prev };
      let advancedAny = false;

      for (const [id, node] of Object.entries(next)) {
        if (node.status === 'READY') {
          next[id] = { ...node, status: 'RUNNING' };
          advancedAny = true;
          break;
        }
        if (node.status === 'RUNNING') {
          next[id] = { ...node, status: 'COMPLETED', outputs: { result: 'ok' } };
          advancedAny = true;
          break;
        }
        if (node.status === 'PENDING') {
          const allDepsDone = node.dependencies.every(
            (depId) => next[depId]?.status === 'COMPLETED',
          );
          if (allDepsDone) {
            next[id] = { ...node, status: 'READY' };
            advancedAny = true;
            break;
          }
        }
      }

      if (advancedAny) {
        setNotification('Orchestrator stepped forward: updated ready nodes');
      } else {
        setNotification('No eligible nodes to advance at this time');
      }
      return next;
    });
  };

  const completedCount = Object.values(nodes).filter((n) => n.status === 'COMPLETED').length;
  const failedCount = Object.values(nodes).filter(
    (n) => n.status === 'FAILED' || n.status === 'REJECTED_LOOPBACK',
  ).length;
  const totalCount = Object.keys(nodes).length;

  return (
    <section
      aria-labelledby={cardTitleId}
      className="p-4 my-3 bg-zinc-900 border border-zinc-800 rounded-xl text-zinc-100 shadow-md text-xs font-mono space-y-4"
    >
      <header className="flex items-center justify-between border-b border-zinc-800 pb-2">
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
          <h3 id={cardTitleId} className="font-semibold text-sm text-zinc-100">
            DAG Visual Orchestrator & Cold Resume
          </h3>
          <span className="text-[10px] px-2 py-0.5 rounded bg-zinc-800 text-zinc-400">
            {workflowId}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-zinc-400">
            Progress: {completedCount}/{totalCount} Completed
          </span>
          {failedCount > 0 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-rose-950 text-rose-300 border border-rose-800">
              {failedCount} Issue(s)
            </span>
          )}
        </div>
      </header>

      {/* Action Toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={handleAdvanceStep}
          className="px-3 py-1.5 rounded bg-blue-600 hover:bg-blue-500 text-white font-medium transition-colors"
        >
          Advance Step
        </button>
        <button
          type="button"
          onClick={handleColdResume}
          disabled={isResuming}
          className="px-3 py-1.5 rounded bg-emerald-700 hover:bg-emerald-600 text-white font-medium transition-colors"
        >
          {isResuming ? 'Resuming...' : 'Cold Resume Checkpoint'}
        </button>
        <button
          type="button"
          onClick={() => setShowRejectForm((prev) => !prev)}
          className="px-3 py-1.5 rounded bg-purple-800 hover:bg-purple-700 text-white font-medium transition-colors"
        >
          {showRejectForm ? 'Close Reject Panel' : 'Bidirectional Reject & Redo'}
        </button>
      </div>

      {/* Reject Loopback Panel */}
      {showRejectForm && (
        <form
          onSubmit={handleExecuteRejectLoopback}
          className="p-3 bg-zinc-950 border border-purple-800/60 rounded-lg space-y-3"
        >
          <div className="text-[11px] font-semibold text-purple-300">
            Downstream Critic Reject & Cascade Redo
          </div>
          <div className="space-y-1">
            <label htmlFor="reject-target-select" className="block text-[11px] text-zinc-400">
              Target Node to Reject:
            </label>
            <select
              id="reject-target-select"
              value={rejectTargetId}
              onChange={(e) => setRejectTargetId(e.target.value)}
              className="w-full bg-zinc-900 border border-zinc-700 rounded p-1.5 text-xs text-zinc-200"
            >
              {Object.values(nodes).map((node) => (
                <option key={node.id} value={node.id}>
                  {node.name} ({node.id}) - {node.status}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <label htmlFor="reject-feedback-input" className="block text-[11px] text-zinc-400">
              Audit Feedback & Defects:
            </label>
            <input
              id="reject-feedback-input"
              type="text"
              value={rejectFeedback}
              onChange={(e) => setRejectFeedback(e.target.value)}
              className="w-full bg-zinc-900 border border-zinc-700 rounded p-1.5 text-xs text-zinc-200"
            />
          </div>
          <div className="flex gap-2">
            <button
              type="submit"
              className="px-3 py-1 rounded bg-rose-700 hover:bg-rose-600 text-white transition-colors text-xs"
            >
              Confirm Reject & Cascade Reset
            </button>
            <button
              type="button"
              onClick={() => setShowRejectForm(false)}
              className="px-2 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs"
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {/* DAG Node Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        {Object.values(nodes).map((node) => {
          const isSelected = selectedNodeId === node.id;
          return (
            <button
              type="button"
              key={node.id}
              onClick={() => setSelectedNodeId(isSelected ? null : node.id)}
              className={`p-3 rounded-lg border transition-all cursor-pointer text-left w-full ${
                STATUS_COLOR_MAP[node.status]
              } ${isSelected ? 'ring-2 ring-blue-500' : ''}`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="font-bold text-xs">{node.name}</span>
                <span className="text-[10px] px-1.5 py-0.2 rounded border bg-black/40">
                  {node.status}
                </span>
              </div>
              <div className="text-[10px] text-zinc-400 flex items-center justify-between">
                <span>Agent: {node.assignedSubagent}</span>
                <span>Type: {node.nodeType}</span>
              </div>
              <div className="text-[10px] text-zinc-400 mt-1">
                Dependencies:{' '}
                {node.dependencies.length > 0 ? node.dependencies.join(', ') : 'None (Root)'}
              </div>
              {node.errorMessage && (
                <div className="mt-1 text-[10px] text-rose-400 bg-rose-950/60 p-1 rounded border border-rose-900">
                  Error: {node.errorMessage}
                </div>
              )}
              {node.feedbackHistory.length > 0 && (
                <div className="mt-1 text-[10px] text-purple-300 bg-purple-950/40 p-1 rounded border border-purple-900">
                  Feedback: {node.feedbackHistory[node.feedbackHistory.length - 1]}
                </div>
              )}
            </button>
          );
        })}
      </div>

      {/* Screen Reader & Activity Output */}
      <footer className="pt-2 border-t border-zinc-800 flex items-center justify-between text-[11px] text-zinc-400">
        <span>Chat: {chatId}</span>
        <output aria-live="polite" className="text-zinc-300">
          {notification}
        </output>
      </footer>
    </section>
  );
};
