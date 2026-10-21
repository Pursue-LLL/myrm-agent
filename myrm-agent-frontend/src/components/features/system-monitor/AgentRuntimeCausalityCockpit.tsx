/**
 * [INPUT]: RuntimeCausalitySnapshotItem, ReapOrphans action callback, and loading flags.
 * [OUTPUT]: High-density industrial activity-monitor style AgentRuntimeCausalityCockpit component.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/AgentRuntimeCausalityCockpit.tsx
 */

import React, { useState } from 'react';
import {
  AgentRuntimeCausalityCockpitProps,
  ProcessCausalityNodeItem,
  ProcessLifecycleStateType,
} from './runtimeZombieReaperTypes';

export const AgentRuntimeCausalityCockpit: React.FC<AgentRuntimeCausalityCockpitProps> = ({
  snapshot,
  onReapOrphans,
  onRefresh,
  isLoading = false,
}) => {
  const [selectedProfile, setSelectedProfile] = useState<string>('all');
  const [activeTab, setActiveTab] = useState<'tree' | 'profiles' | 'failures'>('tree');
  const [reapingParentId, setReapingParentId] = useState<string | null>(null);

  const getStatusBadge = (state: ProcessLifecycleStateType) => {
    switch (state) {
      case 'running':
        return <span className="px-2 py-0.5 rounded text-xs font-semibold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">RUNNING</span>;
      case 'idle':
        return <span className="px-2 py-0.5 rounded text-xs font-semibold bg-blue-500/20 text-blue-400 border border-blue-500/30">IDLE</span>;
      case 'crashed':
        return <span className="px-2 py-0.5 rounded text-xs font-semibold bg-rose-500/20 text-rose-400 border border-rose-500/30">CRASHED</span>;
      case 'orphan':
        return <span className="px-2 py-0.5 rounded text-xs font-semibold bg-amber-500/20 text-amber-400 border border-amber-500/30">ORPHAN</span>;
      case 'deadlocked':
        return <span className="px-2 py-0.5 rounded text-xs font-semibold bg-purple-500/20 text-purple-400 border border-purple-500/30">DEADLOCKED</span>;
      case 'terminated':
      default:
        return <span className="px-2 py-0.5 rounded text-xs font-semibold bg-zinc-500/20 text-zinc-400 border border-zinc-500/30">TERMINATED</span>;
    }
  };

  const filteredNodes = selectedProfile === 'all'
    ? snapshot.nodes
    : snapshot.nodes.filter((n) => n.profile_id === selectedProfile);

  const handleReap = async (parentId: string) => {
    if (!onReapOrphans) return;
    setReapingParentId(parentId);
    try {
      await onReapOrphans(parentId);
    } finally {
      setReapingParentId(null);
    }
  };

  // Group into root and children
  const rootNodes = filteredNodes.filter((n) => !n.parent_id);
  const childMap = filteredNodes.reduce<Record<string, ProcessCausalityNodeItem[]>>((acc, node) => {
    if (node.parent_id) {
      if (!acc[node.parent_id]) acc[node.parent_id] = [];
      acc[node.parent_id].push(node);
    }
    return acc;
  }, {});

  return (
    <div className="w-full bg-zinc-950 text-zinc-100 border border-zinc-800 rounded-xl p-5 shadow-2xl space-y-5 font-mono">
      {/* Header bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-zinc-800 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xl font-bold tracking-tight text-white">⚡ Agent Runtime Causality Cockpit</span>
            <span className="text-xs px-2 py-0.5 bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 rounded">
              PGID Reaper v2.4
            </span>
          </div>
          <p className="text-xs text-zinc-400 mt-1">
            Real-time process tree causality tracing, orphan reaper watchdog, and post-mortem run diagnostics.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {onRefresh && (
            <button
              onClick={() => onRefresh()}
              disabled={isLoading}
              className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-xs text-zinc-200 rounded border border-zinc-700 transition disabled:opacity-50"
            >
              {isLoading ? 'Refreshing...' : '🔄 Refresh Snapshot'}
            </button>
          )}
        </div>
      </div>

      {/* Top Stat Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-zinc-900/80 border border-zinc-800/80 rounded-lg p-3">
          <div className="text-xs text-zinc-400">Active Process Nodes</div>
          <div className="text-xl font-bold text-emerald-400 mt-0.5">{snapshot.nodes.length}</div>
        </div>
        <div className="bg-zinc-900/80 border border-zinc-800/80 rounded-lg p-3">
          <div className="text-xs text-zinc-400">Total Orphans Reaped</div>
          <div className="text-xl font-bold text-amber-400 mt-0.5">{snapshot.total_reaped_orphans}</div>
        </div>
        <div className="bg-zinc-900/80 border border-zinc-800/80 rounded-lg p-3">
          <div className="text-xs text-zinc-400">Deadlocks Tripped</div>
          <div className="text-xl font-bold text-purple-400 mt-0.5">{snapshot.total_deadlocks_broken}</div>
        </div>
        <div className="bg-zinc-900/80 border border-zinc-800/80 rounded-lg p-3">
          <div className="text-xs text-zinc-400">Post-Mortem Failures</div>
          <div className="text-xl font-bold text-rose-400 mt-0.5">{snapshot.recent_failed_tasks.length}</div>
        </div>
      </div>

      {/* Tab Navigation & Filters */}
      <div className="flex items-center justify-between border-b border-zinc-800/80 pb-2">
        <div className="flex gap-2">
          <button
            onClick={() => setActiveTab('tree')}
            className={`px-3 py-1 rounded text-xs font-medium transition ${
              activeTab === 'tree' ? 'bg-indigo-600 text-white' : 'bg-zinc-900 text-zinc-400 hover:text-zinc-200'
            }`}
          >
            Process Tree ({snapshot.nodes.length})
          </button>
          <button
            onClick={() => setActiveTab('profiles')}
            className={`px-3 py-1 rounded text-xs font-medium transition ${
              activeTab === 'profiles' ? 'bg-indigo-600 text-white' : 'bg-zinc-900 text-zinc-400 hover:text-zinc-200'
            }`}
          >
            Profile Quotas ({snapshot.profile_summaries.length})
          </button>
          <button
            onClick={() => setActiveTab('failures')}
            className={`px-3 py-1 rounded text-xs font-medium transition ${
              activeTab === 'failures' ? 'bg-indigo-600 text-white' : 'bg-zinc-900 text-zinc-400 hover:text-zinc-200'
            }`}
          >
            Failures Archive ({snapshot.recent_failed_tasks.length})
          </button>
        </div>

        {activeTab === 'tree' && (
          <div className="flex items-center gap-2 text-xs">
            <span className="text-zinc-500">Filter Profile:</span>
            <select
              value={selectedProfile}
              aria-label="Filter Profile"
              onChange={(e) => setSelectedProfile(e.target.value)}
              className="bg-zinc-900 border border-zinc-700 text-zinc-200 rounded px-2 py-0.5"
            >
              <option value="all">All Profiles</option>
              {snapshot.profile_summaries.map((p) => (
                <option key={p.profile_id} value={p.profile_id}>
                  {p.profile_id}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* Main Content Area */}
      {activeTab === 'tree' && (
        <div className="space-y-3">
          {filteredNodes.length === 0 ? (
            <div className="text-center py-10 text-zinc-500 text-sm">
              No active agent or helper processes recorded.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border border-zinc-800/80 rounded-lg">
                <thead className="bg-zinc-900/90 text-zinc-400 uppercase border-b border-zinc-800">
                  <tr>
                    <th className="py-2.5 px-3">Node Name &amp; ID</th>
                    <th className="py-2.5 px-2">Role</th>
                    <th className="py-2.5 px-2">PID / PGID</th>
                    <th className="py-2.5 px-2">Status</th>
                    <th className="py-2.5 px-2">CPU</th>
                    <th className="py-2.5 px-2">RSS (MB)</th>
                    <th className="py-2.5 px-2">Tokens</th>
                    <th className="py-2.5 px-2 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/60 bg-zinc-950/40">
                  {rootNodes.map((root) => (
                    <React.Fragment key={root.node_id}>
                      <tr className="hover:bg-zinc-900/40">
                        <td className="py-2.5 px-3">
                          <div className="font-semibold text-white flex items-center gap-1.5">
                            <span>👑</span> {root.name}
                          </div>
                          <div className="text-[10px] text-zinc-500">{root.node_id}</div>
                        </td>
                        <td className="py-2.5 px-2 text-zinc-300">{root.role}</td>
                        <td className="py-2.5 px-2 text-zinc-400">
                          {root.pid} / <span className="text-zinc-500">{root.pgid}</span>
                        </td>
                        <td className="py-2.5 px-2">{getStatusBadge(root.state)}</td>
                        <td className="py-2.5 px-2 text-zinc-300">{root.cpu_percent.toFixed(1)}%</td>
                        <td className="py-2.5 px-2 text-zinc-300">{root.memory_rss_mb.toFixed(1)} MB</td>
                        <td className="py-2.5 px-2 text-zinc-300">{root.tokens_consumed.toLocaleString()}</td>
                        <td className="py-2.5 px-2 text-right">
                          {onReapOrphans && (
                            <button
                              onClick={() => handleReap(root.node_id)}
                              disabled={reapingParentId === root.node_id}
                              className="px-2 py-0.5 text-[11px] bg-rose-950/60 hover:bg-rose-900 border border-rose-800/70 text-rose-300 rounded transition disabled:opacity-50"
                            >
                              {reapingParentId === root.node_id ? 'Reaping...' : 'Reap Orphans'}
                            </button>
                          )}
                        </td>
                      </tr>

                      {/* Descendants of root */}
                      {(childMap[root.node_id] || []).map((child) => (
                        <tr key={child.node_id} className="bg-zinc-900/20 hover:bg-zinc-900/50">
                          <td className="py-2 px-3 pl-8">
                            <div className="text-zinc-200 flex items-center gap-1.5">
                              <span className="text-zinc-500">└── ↳</span> {child.name}
                            </div>
                            <div className="text-[10px] text-zinc-500 pl-4">{child.node_id}</div>
                          </td>
                          <td className="py-2 px-2 text-zinc-400">{child.role}</td>
                          <td className="py-2 px-2 text-zinc-400">
                            {child.pid} / <span className="text-zinc-500">{child.pgid}</span>
                          </td>
                          <td className="py-2 px-2">{getStatusBadge(child.state)}</td>
                          <td className="py-2 px-2 text-zinc-400">{child.cpu_percent.toFixed(1)}%</td>
                          <td className="py-2 px-2 text-zinc-400">{child.memory_rss_mb.toFixed(1)} MB</td>
                          <td className="py-2 px-2 text-zinc-400">{child.tokens_consumed.toLocaleString()}</td>
                          <td className="py-2 px-2 text-right text-zinc-600">—</td>
                        </tr>
                      ))}
                    </React.Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Profiles Breakdown Tab */}
      {activeTab === 'profiles' && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {snapshot.profile_summaries.map((prof) => (
            <div key={prof.profile_id} className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-4 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-bold text-white text-sm">📁 {prof.profile_id}</span>
                <span className="text-xs px-2 py-0.5 rounded bg-zinc-800 text-zinc-300">
                  {prof.active_processes} procs
                </span>
              </div>
              <div className="space-y-1 text-xs text-zinc-400 pt-1">
                <div className="flex justify-between">
                  <span>Aggregated CPU:</span>
                  <span className="text-emerald-400 font-semibold">{prof.total_cpu_percent.toFixed(1)}%</span>
                </div>
                <div className="flex justify-between">
                  <span>Aggregated RSS:</span>
                  <span className="text-blue-400 font-semibold">{prof.total_memory_rss_mb.toFixed(1)} MB</span>
                </div>
                <div className="flex justify-between">
                  <span>Tokens Consumed:</span>
                  <span className="text-indigo-400 font-semibold">{prof.total_tokens_consumed.toLocaleString()}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Failures Archive Tab */}
      {activeTab === 'failures' && (
        <div className="space-y-3">
          {snapshot.recent_failed_tasks.length === 0 ? (
            <div className="text-center py-10 text-zinc-500 text-sm">
              No failed tasks recorded in post-mortem archive.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border border-zinc-800 rounded-lg">
                <thead className="bg-zinc-900/90 text-zinc-400 uppercase border-b border-zinc-800">
                  <tr>
                    <th className="py-2 px-3">Task ID</th>
                    <th className="py-2 px-2">Task Name</th>
                    <th className="py-2 px-2">Profile</th>
                    <th className="py-2 px-2">Exit Code</th>
                    <th className="py-2 px-2">Duration</th>
                    <th className="py-2 px-3">Crash Reason</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800 bg-zinc-950/40">
                  {snapshot.recent_failed_tasks.map((task) => (
                    <tr key={task.task_id} className="hover:bg-zinc-900/40">
                      <td className="py-2 px-3 font-semibold text-rose-300">{task.task_id}</td>
                      <td className="py-2 px-2 text-white">{task.name}</td>
                      <td className="py-2 px-2 text-zinc-400">{task.profile_id}</td>
                      <td className="py-2 px-2">
                        <span className="px-1.5 py-0.5 rounded text-[11px] font-bold bg-rose-500/20 text-rose-400 border border-rose-500/30">
                          {task.exit_code}
                        </span>
                      </td>
                      <td className="py-2 px-2 text-zinc-400">{task.duration_ms} ms</td>
                      <td className="py-2 px-3 text-rose-400 font-mono text-[11px] truncate max-w-xs" title={task.crash_reason}>
                        {task.crash_reason}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
