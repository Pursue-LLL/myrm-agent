'use client';

/**
 * [INPUT]
 * ./workspaceCockpitTypes (POS: WorkspaceTaskItem, SwimlaneType)
 * ./useWorkspaceOfflineDigest (POS: formatTimeDuration)
 * @/lib/utils/classnameUtils (POS: cn helper)
 * lucide-react (POS: ShieldAlert, PlayCircle, Eye, Calendar, Terminal, Check, X, ArrowUpRight, Clock)
 *
 * [OUTPUT]
 * GlobalFourSwimlanesDeck: 4-swimlanes task orchestrator grid with live streaming output tails.
 *
 * [POS]
 * Four-swimlane mission control deck for digital agent workspace. Aligns with LoopX & Hermes v0.21.5.
 */

import React, { useMemo } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import {
  ShieldAlert,
  PlayCircle,
  Eye,
  Calendar,
  Terminal,
  Check,
  X,
  ArrowUpRight,
  Clock,
} from 'lucide-react';
import type { SwimlaneType, WorkspaceTaskItem } from './workspaceCockpitTypes';
import { formatTimeDuration } from './useWorkspaceOfflineDigest';

interface GlobalFourSwimlanesDeckProps {
  tasks: WorkspaceTaskItem[];
  onNavigateToChat: (chatId: string, taskId?: string) => void;
  onApproveDecision?: (taskId: string) => void;
  onRejectDecision?: (taskId: string) => void;
  className?: string;
}

interface SwimlaneConfig {
  id: SwimlaneType;
  title: string;
  badgeColor: string;
  icon: React.ReactNode;
  description: string;
}

export const GlobalFourSwimlanesDeck: React.FC<GlobalFourSwimlanesDeckProps> = ({
  tasks,
  onNavigateToChat,
  onApproveDecision,
  onRejectDecision,
  className,
}) => {
  const lanes: SwimlaneConfig[] = useMemo(
    () => [
      {
        id: 'needs-you',
        title: 'Needs You',
        badgeColor: 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30',
        icon: <ShieldAlert className="w-4 h-4 text-amber-500" />,
        description: 'Waiting for approval & human input',
      },
      {
        id: 'in-progress',
        title: 'In Progress',
        badgeColor: 'bg-primary/15 text-primary border-primary/30',
        icon: <PlayCircle className="w-4 h-4 text-primary" />,
        description: 'Executing autonomously',
      },
      {
        id: 'observing',
        title: 'Observing',
        badgeColor: 'bg-indigo-500/15 text-indigo-500 border-indigo-500/30',
        icon: <Eye className="w-4 h-4 text-indigo-500" />,
        description: 'Probes, monitors & health checks',
      },
      {
        id: 'scheduled',
        title: 'Scheduled',
        badgeColor: 'bg-muted text-muted-foreground border-border',
        icon: <Calendar className="w-4 h-4 text-muted-foreground" />,
        description: 'Cron schedules & deferred jobs',
      },
    ],
    [],
  );

  const groupedTasks = useMemo(() => {
    const map = new Map<SwimlaneType, WorkspaceTaskItem[]>();
    for (const lane of lanes) {
      map.set(lane.id, []);
    }
    for (const task of tasks) {
      const list = map.get(task.swimlane);
      if (list) {
        list.push(task);
      }
    }
    return map;
  }, [tasks, lanes]);

  return (
    <div
      data-testid="global-four-swimlanes-deck"
      className={cn('grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4', className)}
    >
      {lanes.map((lane) => {
        const laneTasks = groupedTasks.get(lane.id) ?? [];

        return (
          <section
            key={lane.id}
            data-testid={`swimlane-${lane.id}`}
            aria-label={lane.title}
            className="flex flex-col rounded-xl border border-border/70 bg-card p-3 shadow-xs min-h-[380px]"
          >
            {/* Swimlane Column Header */}
            <div className="flex items-center justify-between pb-2 mb-2 border-b border-border/50">
              <div className="flex items-center gap-1.5 min-w-0">
                {lane.icon}
                <h4 className="text-xs font-semibold text-foreground truncate">{lane.title}</h4>
              </div>
              <span
                className={cn(
                  'px-2 py-0.5 rounded-full text-[11px] font-bold border',
                  lane.badgeColor,
                )}
              >
                {laneTasks.length}
              </span>
            </div>

            {/* Column Description */}
            <p className="text-[11px] text-muted-foreground mb-3">{lane.description}</p>

            {/* Task Cards Stack */}
            <div className="flex-1 space-y-2 overflow-y-auto">
              {laneTasks.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-36 text-center text-muted-foreground/60 border border-dashed border-border/40 rounded-lg p-3">
                  <span className="text-xs">No active items</span>
                </div>
              ) : (
                laneTasks.map((task) => (
                  <div
                    key={task.id}
                    data-testid={`task-card-${task.id}`}
                    className={cn(
                      'group rounded-lg border p-2.5 transition-all text-xs flex flex-col gap-1.5',
                      task.swimlane === 'needs-you'
                        ? 'border-amber-500/40 bg-amber-500/5 hover:border-amber-500/70 shadow-xs'
                        : 'border-border/60 bg-background hover:border-border hover:shadow-xs',
                    )}
                  >
                    {/* Title and navigation link */}
                    <div className="flex items-start justify-between gap-2">
                      <span className="font-semibold text-foreground line-clamp-2" title={task.title}>
                        {task.title}
                      </span>
                      <button
                        type="button"
                        onClick={() => onNavigateToChat(task.chatId, task.id)}
                        className="p-1 rounded text-muted-foreground hover:text-primary transition-colors shrink-0"
                        title="Open task session"
                        aria-label="Open task session"
                      >
                        <ArrowUpRight className="w-3.5 h-3.5" />
                      </button>
                    </div>

                    {/* Metadata line */}
                    <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                      {task.agentName && (
                        <span className="truncate max-w-[120px] font-medium text-foreground/80">
                          @{task.agentName}
                        </span>
                      )}
                      {task.waitingDurationMs !== undefined && (
                        <span className="flex items-center gap-1 text-amber-600 dark:text-amber-400 font-medium">
                          <Clock className="w-3 h-3" />
                          Wait {formatTimeDuration(task.waitingDurationMs)}
                        </span>
                      )}
                      {task.scheduleCron && (
                        <span className="font-mono text-[10px] text-muted-foreground">
                          {task.scheduleCron}
                        </span>
                      )}
                    </div>

                    {/* Inline Streaming Output Tail (Hermes v0.21.5 #117464) */}
                    {task.latestOutputTail && (
                      <div
                        data-testid={`task-tail-${task.id}`}
                        className="flex items-center gap-1.5 px-2 py-1 bg-muted/60 rounded text-[11px] font-mono text-muted-foreground truncate"
                        title={task.latestOutputTail}
                      >
                        <Terminal className="w-3 h-3 text-primary shrink-0 animate-pulse" />
                        <span className="truncate">{task.latestOutputTail}</span>
                      </div>
                    )}

                    {/* Needs-you Quick Approval Action Bar */}
                    {task.swimlane === 'needs-you' && (
                      <div className="flex items-center justify-end gap-1.5 pt-1 mt-1 border-t border-amber-500/20">
                        {onRejectDecision && (
                          <button
                            type="button"
                            onClick={() => onRejectDecision(task.id)}
                            className="flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium text-destructive hover:bg-destructive/10 transition-colors"
                          >
                            <X className="w-3 h-3" />
                            Reject
                          </button>
                        )}
                        {onApproveDecision && (
                          <button
                            type="button"
                            onClick={() => onApproveDecision(task.id)}
                            className="flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-amber-500 text-white hover:bg-amber-600 transition-colors shadow-xs"
                          >
                            <Check className="w-3 h-3" />
                            Approve
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </section>
        );
      })}
    </div>
  );
};

export default React.memo(GlobalFourSwimlanesDeck);
