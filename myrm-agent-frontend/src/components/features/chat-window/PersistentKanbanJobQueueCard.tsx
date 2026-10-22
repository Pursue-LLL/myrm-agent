import React, { useState, useId } from 'react';
import {
  KanbanJobItem,
  KanbanJobStatus,
  BatchRunnerStatus,
  DEFAULT_KANBAN_JOBS,
} from './kanban-queue/types';

interface PersistentKanbanJobQueueCardProps {
  chatId?: string;
  initialJobs?: KanbanJobItem[];
  onDispatchWave?: (dispatchedCount: number) => void;
  onExportTrajectories?: (count: number) => void;
}

const STATUS_COLOR_MAP: Record<KanbanJobStatus, string> = {
  triage: 'bg-zinc-800 text-zinc-300 border-zinc-700',
  todo: 'bg-slate-900 text-slate-300 border-slate-700',
  ready: 'bg-blue-950 text-blue-300 border-blue-700',
  running: 'bg-amber-950 text-amber-300 border-amber-700 animate-pulse',
  done: 'bg-emerald-950 text-emerald-300 border-emerald-700',
  blocked: 'bg-rose-950 text-rose-300 border-rose-700',
};

export const PersistentKanbanJobQueueCard: React.FC<PersistentKanbanJobQueueCardProps> = ({
  chatId = 'chat-default',
  initialJobs = DEFAULT_KANBAN_JOBS,
  onDispatchWave,
  onExportTrajectories,
}) => {
  const cardTitleId = useId();
  const [jobs, setJobs] = useState<KanbanJobItem[]>(initialJobs);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [circuitBreakerEnabled, setCircuitBreakerEnabled] = useState(true);
  const [notification, setNotification] = useState('Persistent Kanban Queue ready');

  const batchStatus: BatchRunnerStatus = {
    totalJobs: jobs.length,
    doneJobs: jobs.filter((j) => j.status === 'done').length,
    readyJobs: jobs.filter((j) => j.status === 'ready').length,
    runningJobs: jobs.filter((j) => j.status === 'running').length,
    blockedJobs: jobs.filter((j) => j.status === 'blocked').length,
    resumeAvailable: jobs.some((j) => j.status === 'done') && jobs.some((j) => j.status === 'ready'),
    trajectoriesCollected: jobs.filter((j) => j.status === 'done').length,
  };

  const handleClaim = (jobId: string) => {
    setJobs((prev) =>
      prev.map((job) => {
        if (job.jobId === jobId) {
          return {
            ...job,
            status: 'running',
            assignee: 'worker-slot-rr-1',
            lastHeartbeatTimestamp: Date.now(),
            updatedAt: Date.now(),
          };
        }
        return job;
      }),
    );
    setNotification(`Job [${jobId}] claimed by worker-slot-rr-1 and running in Git worktree`);
  };

  const handleComplete = (jobId: string) => {
    setJobs((prev) => {
      const next = prev.map((job) => {
        if (job.jobId === jobId) {
          return {
            ...job,
            status: 'done' as const,
            resultSummary: 'Task verified & criteria satisfied',
            updatedAt: Date.now(),
          };
        }
        return job;
      });

      // Automatically unblock downstream dependents whose dependencies are all done
      return next.map((job) => {
        if (job.status === 'todo') {
          const allDepsDone = job.dependencies.every((depId) =>
            next.some((d) => d.jobId === depId && d.status === 'done'),
          );
          if (allDepsDone) {
            return { ...job, status: 'ready' as const, updatedAt: Date.now() };
          }
        }
        return job;
      });
    });
    setNotification(`Job [${jobId}] completed. Dependent downstream tasks unblocked.`);
  };

  const handleToggleBlock = (jobId: string) => {
    setJobs((prev) =>
      prev.map((job) => {
        if (job.jobId === jobId) {
          if (job.status === 'blocked') {
            return {
              ...job,
              status: 'ready',
              blockedReason: undefined,
              updatedAt: Date.now(),
            };
          }
          return {
            ...job,
            status: 'blocked',
            blockedReason: 'Manual operator pause requested',
            updatedAt: Date.now(),
          };
        }
        return job;
      }),
    );
    setNotification(`Job [${jobId}] block state toggled.`);
  };

  const handleHeartbeat = (jobId: string) => {
    setJobs((prev) =>
      prev.map((job) => {
        if (job.jobId === jobId) {
          return { ...job, lastHeartbeatTimestamp: Date.now() };
        }
        return job;
      }),
    );
    setNotification(`Heartbeat acknowledged for [${jobId}]. 4h watchdog timer renewed.`);
  };

  const handleDispatch12Wave = () => {
    let count = 0;
    setJobs((prev) =>
      prev.map((job) => {
        if (job.status === 'ready' && count < 12) {
          count += 1;
          return {
            ...job,
            status: 'running',
            assignee: `worker-slot-rr-${count}`,
            lastHeartbeatTimestamp: Date.now(),
            updatedAt: Date.now(),
          };
        }
        return job;
      }),
    );
    setNotification(`12-Way parallel wave dispatched: ${count} worker instances active.`);
    onDispatchWave?.(count);
  };

  const handleExportTrajectories = () => {
    const exportedCount = batchStatus.trajectoriesCollected;
    setNotification(`Exported ${exportedCount} HuggingFace JSONL trajectories with zero loss.`);
    onExportTrajectories?.(exportedCount);
  };

  const handleToggleCircuitBreaker = () => {
    setCircuitBreakerEnabled((prev) => !prev);
    setNotification(
      `Hot circuit breaker ${!circuitBreakerEnabled ? 'ENABLED (Safe)' : 'DISABLED (Fan-out locked)'}`,
    );
  };

  return (
    <section
      aria-labelledby={cardTitleId}
      className="p-4 my-3 bg-zinc-900 border border-zinc-800 rounded-xl text-zinc-100 shadow-md text-xs font-mono space-y-4"
    >
      <header className="flex flex-wrap items-center justify-between border-b border-zinc-800 pb-2 gap-2">
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-blue-500 animate-pulse" />
          <h3 id={cardTitleId} className="font-semibold text-sm text-zinc-100">
            Persistent Kanban Job Queue & 12-Way Batch Runner
          </h3>
          <span className="text-[10px] px-2 py-0.5 rounded bg-zinc-800 text-zinc-400">
            {chatId}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-zinc-400">
            Done: {batchStatus.doneJobs}/{batchStatus.totalJobs} | Ready: {batchStatus.readyJobs} | Running: {batchStatus.runningJobs}
          </span>
          <button
            type="button"
            onClick={handleToggleCircuitBreaker}
            className={`text-[10px] px-2 py-0.5 rounded font-medium border transition-colors ${
              circuitBreakerEnabled
                ? 'bg-emerald-950 text-emerald-300 border-emerald-800 hover:bg-emerald-900'
                : 'bg-rose-950 text-rose-300 border-rose-800 hover:bg-rose-900'
            }`}
          >
            Circuit Breaker: {circuitBreakerEnabled ? 'ACTIVE' : 'OFF'}
          </button>
        </div>
      </header>

      {/* Action Toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={handleDispatch12Wave}
          className="px-3 py-1.5 rounded bg-blue-600 hover:bg-blue-500 text-white font-medium transition-colors"
        >
          Dispatch 12-Way Wave
        </button>
        <button
          type="button"
          onClick={handleExportTrajectories}
          className="px-3 py-1.5 rounded bg-purple-700 hover:bg-purple-600 text-white font-medium transition-colors"
        >
          Export HF JSONL Trajectories
        </button>
      </div>

      {/* Kanban Job Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
        {jobs.map((job) => {
          const isSelected = selectedJobId === job.jobId;
          return (
            <div
              key={job.jobId}
              className={`p-3 rounded-lg border transition-all text-left flex flex-col justify-between ${
                STATUS_COLOR_MAP[job.status]
              } ${isSelected ? 'ring-2 ring-blue-500' : ''}`}
            >
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="font-bold text-xs truncate max-w-[170px]" title={job.title}>
                    {job.title}
                  </span>
                  <span className="text-[10px] px-1.5 py-0.2 rounded border bg-black/40 uppercase">
                    {job.status}
                  </span>
                </div>
                <div className="text-[10px] text-zinc-400">
                  <span>Stage: {job.stage}</span>
                </div>
                <div className="text-[10px] text-zinc-400 mt-1 line-clamp-2">
                  Goal: {job.goal}
                </div>
                {job.assignee && (
                  <div className="text-[10px] text-zinc-400 mt-0.5">
                    Worker: <span className="text-zinc-200">{job.assignee}</span>
                  </div>
                )}
                {job.worktreePath && (
                  <div className="text-[9px] text-zinc-500 mt-0.5 truncate">
                    Worktree: {job.worktreePath}
                  </div>
                )}
                {job.blockedReason && (
                  <div className="mt-1 text-[10px] text-rose-300 bg-rose-950/60 p-1 rounded border border-rose-900">
                    Blocked: {job.blockedReason}
                  </div>
                )}
                {job.resultSummary && (
                  <div className="mt-1 text-[10px] text-emerald-300 bg-emerald-950/40 p-1 rounded border border-emerald-900">
                    Result: {job.resultSummary}
                  </div>
                )}
              </div>

              {/* Action buttons per job */}
              <div className="flex flex-wrap items-center gap-1.5 mt-3 pt-2 border-t border-white/10">
                {job.status === 'ready' && (
                  <button
                    type="button"
                    onClick={() => handleClaim(job.jobId)}
                    className="px-2 py-0.5 rounded bg-blue-600 hover:bg-blue-500 text-white text-[10px]"
                  >
                    Claim & Run
                  </button>
                )}
                {job.status === 'running' && (
                  <>
                    <button
                      type="button"
                      onClick={() => handleComplete(job.jobId)}
                      className="px-2 py-0.5 rounded bg-emerald-600 hover:bg-emerald-500 text-white text-[10px]"
                    >
                      Complete
                    </button>
                    <button
                      type="button"
                      onClick={() => handleHeartbeat(job.jobId)}
                      className="px-1.5 py-0.5 rounded bg-amber-700 hover:bg-amber-600 text-white text-[10px]"
                    >
                      Heartbeat
                    </button>
                  </>
                )}
                <button
                  type="button"
                  onClick={() => handleToggleBlock(job.jobId)}
                  className="px-1.5 py-0.5 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-[10px]"
                >
                  {job.status === 'blocked' ? 'Unblock' : 'Block'}
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedJobId(isSelected ? null : job.jobId)}
                  className="px-1.5 py-0.5 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-400 text-[10px]"
                >
                  {isSelected ? 'Collapse' : 'Inspect'}
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Screen Reader & Activity Output */}
      <footer className="pt-2 border-t border-zinc-800 flex items-center justify-between text-[11px] text-zinc-400">
        <span>Watchdog: 4h Auto-Reclaim Active</span>
        <output aria-live="polite" className="text-zinc-300">
          {notification}
        </output>
      </footer>
    </section>
  );
};
