'use client';

import { useState, useCallback, useEffect } from 'react';
import {
  GitFork,
  Play,
  AlertTriangle,
  CheckCircle2,
  RotateCcw,
  PlusCircle,
  Cpu,
  Layers,
} from 'lucide-react';

export type LaneState = 'idle' | 'running' | 'paused' | 'closed';
export type OpStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';

export interface LaneInfoData {
  lane_id: string;
  display_name: string;
  state: LaneState;
  current_leaf_id: string;
  active_op_id?: string | null;
  total_ops: number;
  created_at: number;
}

export interface LaneOperationData {
  op_id: string;
  lane_id: string;
  name: string;
  payload?: Record<string, string | number | boolean | null>;
  status: OpStatus;
  created_at: number;
  started_at?: number | null;
  completed_at?: number | null;
  error_message?: string | null;
  result_node_id?: string | null;
}

export interface MultiLaneSnapshotData {
  session_id: string;
  lanes: Record<string, LaneInfoData>;
  total_nodes: number;
  active_lanes_count: number;
  recent_op_logs: LaneOperationData[];
}

export interface MultiLaneParallelExecutionCardProps {
  chatId?: string;
  initialSnapshot?: MultiLaneSnapshotData | null;
  onDismiss?: () => void;
}

function createFallbackSnapshot(chatId: string): MultiLaneSnapshotData {
  return {
    session_id: chatId,
    lanes: {
      main: {
        lane_id: 'main',
        display_name: 'Main Channel Lane',
        state: 'idle',
        current_leaf_id: 'root',
        active_op_id: null,
        total_ops: 0,
        created_at: Date.now() / 1000,
      },
    },
    total_nodes: 1,
    active_lanes_count: 0,
    recent_op_logs: [],
  };
}

export function MultiLaneParallelExecutionCard({
  chatId = 'default-chat-session',
  initialSnapshot = null,
  onDismiss,
}: MultiLaneParallelExecutionCardProps) {
  const [snapshot, setSnapshot] = useState<MultiLaneSnapshotData>(() => {
    return initialSnapshot || createFallbackSnapshot(chatId);
  });
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [isConflictAlert, setIsConflictAlert] = useState<boolean>(false);

  useEffect(() => {
    if (initialSnapshot) {
      setSnapshot(initialSnapshot);
    }
  }, [initialSnapshot]);

  const handleCreateThreadLane = useCallback(() => {
    const threadIdx = Object.keys(snapshot.lanes).length;
    const newLaneId = `slack:thread-${threadIdx + 100}`;
    const newLane: LaneInfoData = {
      lane_id: newLaneId,
      display_name: `Thread Discussion #${threadIdx + 100}`,
      state: 'idle',
      current_leaf_id: snapshot.lanes.main?.current_leaf_id || 'root',
      active_op_id: null,
      total_ops: 0,
      created_at: Date.now() / 1000,
    };

    setSnapshot((prev) => ({
      ...prev,
      lanes: {
        ...prev.lanes,
        [newLaneId]: newLane,
      },
    }));
    setStatusMessage(`Created thread lane '${newLaneId}'`);
    setIsConflictAlert(false);
  }, [snapshot.lanes]);

  const handleDispatchParallelOps = useCallback(() => {
    const now = Date.now() / 1000;
    const updatedLanes = { ...snapshot.lanes };
    const newOps: LaneOperationData[] = [];
    let dispatchedCount = 0;

    for (const laneId of Object.keys(updatedLanes)) {
      const lane = updatedLanes[laneId];
      if (lane && lane.state === 'idle') {
        const opId = `op-${Math.random().toString(36).substring(2, 8)}`;
        const op: LaneOperationData = {
          op_id: opId,
          lane_id: laneId,
          name: `parallel_execution_${laneId}`,
          status: 'running',
          created_at: now,
          started_at: now,
        };
        updatedLanes[laneId] = {
          ...lane,
          state: 'running',
          active_op_id: opId,
          total_ops: lane.total_ops + 1,
        };
        newOps.push(op);
        dispatchedCount += 1;
      }
    }

    if (dispatchedCount === 0) {
      setStatusMessage('No idle lanes available for dispatch.');
      setIsConflictAlert(false);
      return;
    }

    setSnapshot((prev) => ({
      ...prev,
      lanes: updatedLanes,
      active_lanes_count: Object.values(updatedLanes).filter((l) => l.state === 'running').length,
      recent_op_logs: [...newOps, ...prev.recent_op_logs].slice(0, 50),
    }));
    setStatusMessage(`Dispatched parallel operations across ${dispatchedCount} lanes.`);
    setIsConflictAlert(false);
  }, [snapshot.lanes]);

  const handleSimulateConflict = useCallback(() => {
    // Find a running lane or force main into running first
    const runningLaneId = Object.keys(snapshot.lanes).find(
      (id) => snapshot.lanes[id]?.state === 'running'
    );

    if (!runningLaneId) {
      // Put main into running
      const now = Date.now() / 1000;
      const opId = `op-${Math.random().toString(36).substring(2, 8)}`;
      const mainLane = snapshot.lanes.main;
      if (mainLane) {
        setSnapshot((prev) => ({
          ...prev,
          lanes: {
            ...prev.lanes,
            main: {
              ...mainLane,
              state: 'running',
              active_op_id: opId,
              total_ops: mainLane.total_ops + 1,
            },
          },
          active_lanes_count: 1,
          recent_op_logs: [
            {
              op_id: opId,
              lane_id: 'main',
              name: 'initial_open_op',
              status: 'running',
              created_at: now,
              started_at: now,
            },
            ...prev.recent_op_logs,
          ],
        }));
      }
    }

    // Now trigger conflict rejection
    setStatusMessage(
      '409 Conflict: Lane concurrency constraint violated. At most 1 open operation permitted per lane.'
    );
    setIsConflictAlert(true);
  }, [snapshot.lanes]);

  const handleCompleteActiveOps = useCallback(() => {
    const now = Date.now() / 1000;
    const updatedLanes = { ...snapshot.lanes };
    let completedCount = 0;

    for (const laneId of Object.keys(updatedLanes)) {
      const lane = updatedLanes[laneId];
      if (lane && lane.state === 'running') {
        const resultNodeId = `node-${Math.random().toString(36).substring(2, 10)}`;
        updatedLanes[laneId] = {
          ...lane,
          state: 'idle',
          active_op_id: null,
          current_leaf_id: resultNodeId,
        };
        completedCount += 1;
      }
    }

    if (completedCount === 0) {
      setStatusMessage('No active operations to complete.');
      setIsConflictAlert(false);
      return;
    }

    setSnapshot((prev) => ({
      ...prev,
      lanes: updatedLanes,
      total_nodes: prev.total_nodes + completedCount,
      active_lanes_count: 0,
      recent_op_logs: prev.recent_op_logs.map((op) => {
        if (op.status === 'running') {
          return {
            ...op,
            status: 'completed',
            completed_at: now,
            result_node_id: `node-${Math.random().toString(36).substring(2, 10)}`,
          };
        }
        return op;
      }),
    }));
    setStatusMessage(`Completed ${completedCount} operations and advanced shared tree leaves.`);
    setIsConflictAlert(false);
  }, [snapshot.lanes]);

  const handleReset = useCallback(() => {
    setSnapshot(createFallbackSnapshot(chatId));
    setStatusMessage('Multi-lane session coordinator reset.');
    setIsConflictAlert(false);
  }, [chatId]);

  const laneList = Object.values(snapshot.lanes);

  return (
    <dialog
      open
      className="relative flex flex-col w-full max-w-2xl bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-xl shadow-lg p-5 text-zinc-900 dark:text-zinc-100 z-50 overflow-hidden"
      data-testid="multi-lane-execution-card"
    >
      <div className="flex items-center justify-between pb-3 border-b border-zinc-200 dark:border-zinc-800">
        <div className="flex items-center space-x-2">
          <Layers className="w-5 h-5 text-indigo-500" />
          <h3 className="font-semibold text-base">Pi Harness v2 Multi-Lane Parallel Execution</h3>
        </div>
        {onDismiss && (
          <button
            onClick={onDismiss}
            aria-label="Dismiss dialog"
            className="text-xs px-2.5 py-1 rounded bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 dark:hover:bg-zinc-700 text-zinc-600 dark:text-zinc-300 transition-colors"
          >
            Dismiss
          </button>
        )}
      </div>

      <div className="grid grid-cols-3 gap-3 my-4">
        <div className="flex flex-col p-3 rounded-lg bg-indigo-50/60 dark:bg-indigo-950/30 border border-indigo-200/60 dark:border-indigo-800/50">
          <span className="text-xs text-indigo-600 dark:text-indigo-400 font-medium">
            Active Parallel Lanes
          </span>
          <span className="text-xl font-bold mt-1" data-testid="stat-active-lanes">
            {snapshot.active_lanes_count}
          </span>
        </div>
        <div className="flex flex-col p-3 rounded-lg bg-emerald-50/60 dark:bg-emerald-950/30 border border-emerald-200/60 dark:border-emerald-800/50">
          <span className="text-xs text-emerald-600 dark:text-emerald-400 font-medium">
            Shared Tree Nodes
          </span>
          <span className="text-xl font-bold mt-1" data-testid="stat-total-nodes">
            {snapshot.total_nodes}
          </span>
        </div>
        <div className="flex flex-col p-3 rounded-lg bg-zinc-50 dark:bg-zinc-800/50 border border-zinc-200 dark:border-zinc-700">
          <span className="text-xs text-zinc-500 font-medium">Registered Lanes</span>
          <span className="text-xl font-bold mt-1" data-testid="stat-total-lanes">
            {laneList.length}
          </span>
        </div>
      </div>

      {statusMessage && (
        <output
          className={`text-xs p-2.5 rounded-lg mb-3 flex items-center space-x-2 border ${
            isConflictAlert
              ? 'bg-amber-50 dark:bg-amber-950/40 border-amber-300 dark:border-amber-700/60 text-amber-800 dark:text-amber-200'
              : 'bg-zinc-100 dark:bg-zinc-800/60 border-zinc-200 dark:border-zinc-700 text-zinc-700 dark:text-zinc-300'
          }`}
          data-testid="status-message"
        >
          {isConflictAlert ? (
            <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0" />
          ) : (
            <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
          )}
          <span>{statusMessage}</span>
        </output>
      )}

      <div className="flex flex-wrap items-center gap-2 mb-4">
        <button
          onClick={handleCreateThreadLane}
          className="flex items-center space-x-1.5 text-xs px-3 py-1.5 rounded-md bg-indigo-600 hover:bg-indigo-700 text-white font-medium transition-colors"
          data-testid="btn-create-lane"
        >
          <PlusCircle className="w-3.5 h-3.5" />
          <span>New Thread Lane</span>
        </button>
        <button
          onClick={handleDispatchParallelOps}
          className="flex items-center space-x-1.5 text-xs px-3 py-1.5 rounded-md bg-emerald-600 hover:bg-emerald-700 text-white font-medium transition-colors"
          data-testid="btn-dispatch-parallel"
        >
          <Play className="w-3.5 h-3.5" />
          <span>Dispatch Parallel Ops</span>
        </button>
        <button
          onClick={handleSimulateConflict}
          className="flex items-center space-x-1.5 text-xs px-3 py-1.5 rounded-md bg-amber-600 hover:bg-amber-700 text-white font-medium transition-colors"
          data-testid="btn-simulate-conflict"
        >
          <AlertTriangle className="w-3.5 h-3.5" />
          <span>Simulate Conflict (409)</span>
        </button>
        <button
          onClick={handleCompleteActiveOps}
          className="flex items-center space-x-1.5 text-xs px-3 py-1.5 rounded-md bg-zinc-700 hover:bg-zinc-600 text-white font-medium transition-colors"
          data-testid="btn-complete-ops"
        >
          <Cpu className="w-3.5 h-3.5" />
          <span>Complete Active</span>
        </button>
        <button
          onClick={handleReset}
          className="flex items-center space-x-1.5 text-xs px-2.5 py-1.5 rounded-md bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 dark:hover:bg-zinc-700 text-zinc-600 dark:text-zinc-300 font-medium transition-colors"
          data-testid="btn-reset"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          <span>Reset</span>
        </button>
      </div>

      <div className="space-y-2 mb-4 max-h-48 overflow-y-auto">
        <span className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">
          Active Lanes Topology
        </span>
        <div className="space-y-1.5" data-testid="lanes-list">
          {laneList.map((lane) => (
            <div
              key={lane.lane_id}
              className="flex items-center justify-between p-2 rounded-md bg-zinc-50 dark:bg-zinc-800/40 border border-zinc-200 dark:border-zinc-800 text-xs"
              data-testid={`lane-item-${lane.lane_id}`}
            >
              <div className="flex items-center space-x-2">
                <GitFork className="w-3.5 h-3.5 text-zinc-400" />
                <span className="font-semibold">{lane.display_name}</span>
                <span className="text-zinc-400">({lane.lane_id})</span>
              </div>
              <div className="flex items-center space-x-3">
                <span className="text-zinc-400">Leaf: {lane.current_leaf_id.substring(0, 10)}</span>
                <span
                  className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${
                    lane.state === 'running'
                      ? 'bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300'
                      : 'bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300'
                  }`}
                >
                  {lane.state}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </dialog>
  );
}
