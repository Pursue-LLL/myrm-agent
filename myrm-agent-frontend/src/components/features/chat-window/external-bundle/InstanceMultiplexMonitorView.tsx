import React, { useState } from 'react';
import { SubagentInstanceRecord, SubagentInstanceStatus } from './types';

export interface InstanceMultiplexMonitorViewProps {
  instances: SubagentInstanceRecord[];
  terminatingId: string | null;
  onTerminateInstance: (instanceId: string, reason?: string) => Promise<void>;
}

export const InstanceMultiplexMonitorView: React.FC<InstanceMultiplexMonitorViewProps> = ({
  instances,
  terminatingId,
  onTerminateInstance,
}) => {
  const [filter, setFilter] = useState<'all' | 'active' | 'completed' | 'failed'>('all');
  const [expandedLogs, setExpandedLogs] = useState<Record<string, boolean>>({});

  const toggleLog = (instanceId: string) => {
    setExpandedLogs((prev) => ({
      ...prev,
      [instanceId]: !prev[instanceId],
    }));
  };

  const filteredInstances = instances.filter((inst) => {
    if (filter === 'active') {
      return inst.status === 'running' || inst.status === 'pending';
    }
    if (filter === 'completed') {
      return inst.status === 'completed';
    }
    if (filter === 'failed') {
      return inst.status === 'failed' || inst.status === 'terminated';
    }
    return true;
  });

  const getStatusBadge = (status: SubagentInstanceStatus) => {
    switch (status) {
      case 'running':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-blue-500/10 px-2 py-0.5 text-[11px] font-medium text-blue-500 border border-blue-500/20">
            <span className="h-1.5 w-1.5 rounded-full bg-blue-500 animate-pulse" />
            Running
          </span>
        );
      case 'completed':
        return (
          <span className="inline-flex items-center rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] font-medium text-emerald-500 border border-emerald-500/20">
            ✓ Completed
          </span>
        );
      case 'failed':
        return (
          <span className="inline-flex items-center rounded-full bg-rose-500/10 px-2 py-0.5 text-[11px] font-medium text-rose-500 border border-rose-500/20">
            ✕ Failed
          </span>
        );
      case 'terminated':
        return (
          <span className="inline-flex items-center rounded-full bg-amber-500/10 px-2 py-0.5 text-[11px] font-medium text-amber-500 border border-amber-500/20">
            ⏹ Terminated
          </span>
        );
      case 'pending':
      default:
        return (
          <span className="inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground border border-border">
            ⏳ Pending
          </span>
        );
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-foreground">Multiplexed Subagent Instances</h3>
          <p className="text-xs text-muted-foreground">
            Real-time telemetry, stdout stream inspection, and boundary containment monitor.
          </p>
        </div>

        <div className="flex items-center gap-1 rounded-lg bg-muted/60 p-1 border border-border/30">
          {(['all', 'active', 'completed', 'failed'] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => setFilter(mode)}
              className={`rounded-md px-2 py-0.5 text-[11px] font-medium transition-colors capitalize ${
                filter === mode
                  ? 'bg-background text-foreground shadow-xs'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {mode}
            </button>
          ))}
        </div>
      </div>

      {filteredInstances.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border/60 p-8 text-center">
          <p className="text-xs text-muted-foreground">
            No subagent instances found matching filter &quot;{filter}&quot;.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {filteredInstances.map((inst) => {
            const isExpanded = !!expandedLogs[inst.instance_id];
            const isTerminating = terminatingId === inst.instance_id;
            const canTerminate = inst.status === 'running' || inst.status === 'pending';

            return (
              <div
                key={inst.instance_id}
                className="rounded-lg border border-border/50 bg-card/60 p-3.5 space-y-2.5 shadow-xs"
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-bold text-foreground">
                      {inst.role_label}
                    </span>
                    <span className="text-[11px] font-mono text-muted-foreground">
                      ({inst.bundle_id})
                    </span>
                    {getStatusBadge(inst.status)}
                    {inst.pid > 0 && (
                      <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
                        PID: {inst.pid}
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    {canTerminate && (
                      <button
                        type="button"
                        onClick={() => onTerminateInstance(inst.instance_id, 'user_halted')}
                        disabled={isTerminating}
                        className="rounded border border-rose-500/30 bg-rose-500/10 px-2 py-1 text-[11px] font-medium text-rose-500 hover:bg-rose-500/20 transition-colors disabled:opacity-50"
                      >
                        {isTerminating ? 'Halting...' : 'Halt Instance'}
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => toggleLog(inst.instance_id)}
                      className="rounded border border-border px-2 py-1 text-[11px] font-medium text-foreground hover:bg-muted/40 transition-colors"
                    >
                      {isExpanded ? 'Hide Logs' : `Logs (${inst.stdout_chunks.length})`}
                    </button>
                  </div>
                </div>

                <div className="rounded bg-muted/40 px-2.5 py-1.5 text-xs text-foreground/90 font-mono">
                  <span className="text-muted-foreground mr-1">Workdir:</span>
                  {inst.target_workdir}
                </div>

                <p className="text-xs text-muted-foreground italic">
                  &ldquo;{inst.task_prompt}&rdquo;
                </p>

                {inst.artifacts.length > 0 && (
                  <div className="flex flex-wrap items-center gap-1.5 pt-1">
                    <span className="text-[10px] uppercase font-semibold text-muted-foreground">
                      Artifacts:
                    </span>
                    {inst.artifacts.map((art, idx) => (
                      <span
                        key={idx}
                        className="rounded-full bg-emerald-500/10 px-2 py-0.5 font-mono text-[10px] text-emerald-500 border border-emerald-500/20"
                      >
                        {art.path || art.type}
                      </span>
                    ))}
                  </div>
                )}

                {inst.error && (
                  <div className="rounded border border-rose-500/30 bg-rose-500/10 p-2 text-xs text-rose-500 font-mono">
                    {inst.error}
                  </div>
                )}

                {isExpanded && (
                  <div className="rounded-md bg-zinc-950 p-2.5 font-mono text-[11px] text-zinc-200 border border-zinc-800 space-y-1 max-h-48 overflow-y-auto">
                    {inst.stdout_chunks.length === 0 ? (
                      <span className="text-zinc-500 italic">No output logged yet.</span>
                    ) : (
                      inst.stdout_chunks.map((line, lIdx) => (
                        <div key={lIdx} className="leading-tight">
                          {line}
                        </div>
                      ))
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
