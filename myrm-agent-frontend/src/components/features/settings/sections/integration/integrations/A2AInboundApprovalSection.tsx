'use client';

import { memo, useState, useCallback, useEffect } from 'react';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import {
  ShieldAlert,
  CheckCircle2,
  XCircle,
  Clock,
  RefreshCw,
  ExternalLink,
  MessageSquare,
  Radio,
} from 'lucide-react';
import {
  listPendingA2ATasks,
  approveA2ATask,
  rejectA2ATask,
  type A2APendingTask,
} from '@/services/a2aPeer';

export const A2AInboundApprovalSection = memo(() => {
  const [tasks, setTasks] = useState<A2APendingTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);

  const fetchPendingTasks = useCallback(async () => {
    try {
      setLoading(true);
      const data = await listPendingA2ATasks();
      setTasks(Array.isArray(data) ? data : []);
    } catch {
      setTasks([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPendingTasks();
  }, [fetchPendingTasks]);

  const handleApprove = async (taskId: string) => {
    try {
      setActionLoadingId(taskId);
      await approveA2ATask(taskId);
      await fetchPendingTasks();
    } catch {
      // Handled silently or refreshed
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleReject = async (taskId: string) => {
    try {
      setActionLoadingId(taskId);
      await rejectA2ATask(taskId, 'Rejected by operator in settings panel');
      await fetchPendingTasks();
    } catch {
      // Handled silently or refreshed
    } finally {
      setActionLoadingId(null);
    }
  };

  if (!loading && tasks.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-border/80 bg-muted/20 p-4 text-center">
        <div className="flex items-center justify-center gap-2 text-xs text-muted-foreground">
          <CheckCircle2 className="w-4 h-4 text-emerald-500/80" />
          <span>Zero-Trust Inbox: All inbound peer requests are verified and clear.</span>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ShieldAlert className="w-4 h-4 text-amber-500" />
          <h4 className="text-xs font-semibold uppercase tracking-wider text-amber-600 dark:text-amber-400">
            Pending Inbound Approvals ({tasks.length})
          </h4>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={fetchPendingTasks}
          disabled={loading}
          className="h-7 px-2 text-xs text-muted-foreground hover:text-foreground"
        >
          <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
        </Button>
      </div>

      <div className="space-y-2">
        {tasks.map((task) => {
          const firstMsg = task.messages?.[0]?.content || 'Empty payload';
          const isProcessing = actionLoadingId === task.taskId;
          return (
            <div
              key={task.taskId}
              className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-lg border border-border/60 bg-card p-3 shadow-xs"
            >
              <div className="min-w-0 flex-1 space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs font-medium text-foreground">
                    {task.taskId}
                  </span>
                  <Badge
                    variant="outline"
                    className="border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400 text-[10px]"
                  >
                    pending_approval
                  </Badge>
                  {(task.peer_id || task.peerId) && (
                    <span className="inline-flex items-center gap-1 font-mono text-[10px] text-muted-foreground bg-muted/50 px-1.5 py-0.5 rounded border border-border/40">
                      <Radio className="w-2.5 h-2.5 text-sky-500 shrink-0" />
                      From: {task.peer_id || task.peerId}
                    </span>
                  )}
                  {task.agent_id && (
                    <span className="text-[11px] text-muted-foreground">
                      Target: @{task.agent_id}
                    </span>
                  )}
                  <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
                    <Clock className="w-3 h-3" />
                    {new Date(task.created_at * 1000).toLocaleTimeString()}
                  </span>
                </div>

                <div className="flex items-start gap-1.5 text-xs text-muted-foreground">
                  <MessageSquare className="w-3.5 h-3.5 mt-0.5 shrink-0 text-foreground/40" />
                  <p className="line-clamp-2 break-all text-foreground/80 font-mono text-[11px]">
                    {firstMsg}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2 self-end sm:self-center shrink-0">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={isProcessing}
                  onClick={() => handleReject(task.taskId)}
                  className="h-7 px-2 text-xs border-red-500/30 text-red-600 hover:bg-red-500/10 dark:text-red-400"
                >
                  <XCircle className="w-3.5 h-3.5 mr-1" />
                  Reject
                </Button>
                <Button
                  size="sm"
                  disabled={isProcessing}
                  onClick={() => handleApprove(task.taskId)}
                  className="h-7 px-2.5 text-xs bg-emerald-600 hover:bg-emerald-700 text-white"
                >
                  <CheckCircle2 className="w-3.5 h-3.5 mr-1" />
                  Approve
                </Button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
});

A2AInboundApprovalSection.displayName = 'A2AInboundApprovalSection';
