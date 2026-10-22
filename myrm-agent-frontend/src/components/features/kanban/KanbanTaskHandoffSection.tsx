/**
 * [INPUT]
 * - KanbanTask, TaskStatus, moveTask from '@/services/kanban'
 * - useAgentStore from '@/store/useAgentStore'
 *
 * [OUTPUT]
 * - KanbanTaskHandoffSection: Kanban task handoff & delegation drawer section
 *
 * [POS]
 * Kanban task handoff UI with structured metadata (changed_files & handoff summary),
 * target agent delegation, and timeline visualization of handoff history.
 */

'use client';

import { useState, useMemo } from 'react';
import { toast } from 'sonner';
import { Users, ArrowRight, FileCode, CheckCircle2, ChevronDown, ChevronUp } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import type { KanbanTask, TaskStatus } from '@/services/kanban';
import { moveTask } from '@/services/kanban';
import useAgentStore from '@/store/useAgentStore';

interface HandoffRecord {
  from_agent_id?: string | null;
  to_agent_id?: string | null;
  summary?: string;
  changed_files?: string[];
  timestamp?: string;
}

interface KanbanTaskHandoffSectionProps {
  task: KanbanTask;
  onChanged: () => void;
  t: (key: string) => string;
}

export function KanbanTaskHandoffSection({ task, onChanged, t }: KanbanTaskHandoffSectionProps) {
  const agents = useAgentStore((state) => state.agents);
  const [isExpanded, setIsExpanded] = useState(false);
  const [targetAgentId, setTargetAgentId] = useState<string>('');
  const [targetStatus, setTargetStatus] = useState<TaskStatus>('ready');
  const [summary, setSummary] = useState('');
  const [changedFilesInput, setChangedFilesInput] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const agentMap = useMemo(() => {
    const map = new Map<string, string>();
    agents.forEach((a) => {
      map.set(a.id, a.name);
    });
    return map;
  }, [agents]);

  const currentAgentName = task.agent_id ? agentMap.get(task.agent_id) || task.agent_id : null;

  // Extract structured handoff history
  const handoffHistory = useMemo<HandoffRecord[]>(() => {
    const meta = task.metadata || {};
    const rawHistory = meta.handoff_history;
    if (Array.isArray(rawHistory) && rawHistory.length > 0) {
      return rawHistory as HandoffRecord[];
    }
    const singleHandoff = meta.handoff;
    if (singleHandoff && typeof singleHandoff === 'object') {
      return [singleHandoff as HandoffRecord];
    }
    return [];
  }, [task.metadata]);

  const handleExecuteHandoff = async () => {
    if (!targetAgentId) {
      toast.error(t('handoffSelectAgentRequired'));
      return;
    }

    const files = changedFilesInput
      .split(/[\n,]/)
      .map((f) => f.trim())
      .filter(Boolean);

    setSubmitting(true);
    try {
      await moveTask(task.task_id, targetStatus, {
        assignee_agent_id: targetAgentId,
        result: summary.trim() || undefined,
        metadata: {
          changed_files: files,
          note: summary.trim(),
        },
      });

      toast.success(t('handoffSuccess'));
      setSummary('');
      setChangedFilesInput('');
      setIsExpanded(false);
      onChanged();
    } catch (err) {
      toast.error((err as Error).message || t('handoffFailed'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="rounded-lg border border-border bg-muted/15 p-3 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          <Users className="w-3.5 h-3.5 text-primary" />
          <span>{t('taskHandoff')}</span>
        </div>
        <button
          type="button"
          onClick={() => setIsExpanded(!isExpanded)}
          className="text-[11px] flex items-center gap-1 text-primary hover:underline transition-colors font-medium"
        >
          {isExpanded ? (
            <>
              {t('collapse')}
              <ChevronUp className="w-3 h-3" />
            </>
          ) : (
            <>
              {t('delegateTask')}
              <ChevronDown className="w-3 h-3" />
            </>
          )}
        </button>
      </div>

      {/* Current Assignee Bar */}
      <div className="flex items-center justify-between px-2.5 py-1.5 rounded-md bg-background/80 border text-xs">
        <span className="text-muted-foreground text-[11px]">{t('currentAssignee')}:</span>
        <div className="flex items-center gap-1 font-medium">
          {currentAgentName ? (
            <span className="text-foreground">{currentAgentName}</span>
          ) : (
            <span className="text-muted-foreground italic text-[11px]">{t('unassigned')}</span>
          )}
        </div>
      </div>

      {/* Form when expanded */}
      {isExpanded && (
        <div className="p-2.5 rounded-md border bg-background space-y-2.5 text-xs animate-in fade-in-50 duration-150">
          <div>
            <label className="block text-[10px] font-medium text-muted-foreground mb-1 uppercase tracking-wider">
              {t('transferToAgent')}
            </label>
            <select
              value={targetAgentId}
              onChange={(e) => setTargetAgentId(e.target.value)}
              className="w-full text-xs rounded-md border bg-muted/30 px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="">{t('selectAgentPlaceholder')}</option>
              {agents.map((agent) => (
                <option key={agent.id} value={agent.id} disabled={agent.id === task.agent_id}>
                  {agent.name} {agent.id === task.agent_id ? `(${t('current')})` : ''}
                </option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-[10px] font-medium text-muted-foreground mb-1 uppercase tracking-wider">
                {t('targetStatus')}
              </label>
              <select
                value={targetStatus}
                onChange={(e) => setTargetStatus(e.target.value as TaskStatus)}
                className="w-full text-xs rounded-md border bg-muted/30 px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-primary"
              >
                <option value="ready">{t('statusReady')}</option>
                <option value="backlog">{t('statusBacklog')}</option>
                <option value="in_review">{t('statusInReview')}</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-[10px] font-medium text-muted-foreground mb-1 uppercase tracking-wider">
              {t('handoffSummary')}
            </label>
            <textarea
              rows={2}
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              placeholder={t('handoffSummaryPlaceholder')}
              className="w-full text-xs rounded-md border bg-muted/20 px-2 py-1.5 resize-none focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>

          <div>
            <label className="block text-[10px] font-medium text-muted-foreground mb-1 uppercase tracking-wider flex items-center gap-1">
              <FileCode className="w-3 h-3 text-muted-foreground" />
              <span>{t('changedFilesMetadata')}</span>
            </label>
            <textarea
              rows={2}
              value={changedFilesInput}
              onChange={(e) => setChangedFilesInput(e.target.value)}
              placeholder="src/components/MyComponent.tsx&#10;tests/unit/test_runner.py"
              className="w-full font-mono text-[11px] rounded-md border bg-muted/20 px-2 py-1.5 resize-none focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>

          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={() => setIsExpanded(false)}
              className="px-2.5 py-1 text-xs rounded-md border hover:bg-muted transition-colors"
            >
              {t('cancel')}
            </button>
            <button
              type="button"
              disabled={submitting || !targetAgentId}
              onClick={handleExecuteHandoff}
              className="px-3 py-1 text-xs font-medium rounded-md bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors flex items-center gap-1"
            >
              <CheckCircle2 className="w-3 h-3" />
              {submitting ? t('submitting') : t('confirmHandoff')}
            </button>
          </div>
        </div>
      )}

      {/* Handoff History Timeline */}
      {handoffHistory.length > 0 && (
        <div className="space-y-1.5 pt-1 border-t border-border/60">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground block">
            {t('handoffTimeline')} ({handoffHistory.length})
          </span>
          <div className="space-y-1.5 max-h-36 overflow-y-auto pr-1">
            {handoffHistory.map((rec, idx) => {
              const fromName = rec.from_agent_id
                ? agentMap.get(rec.from_agent_id) || rec.from_agent_id
                : t('unassigned');
              const toName = rec.to_agent_id ? agentMap.get(rec.to_agent_id) || rec.to_agent_id : t('unknown');
              const timeStr = rec.timestamp
                ? new Date(rec.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                : '';

              return (
                <div key={idx} className="p-2 rounded border bg-background/60 text-[11px] space-y-1">
                  <div className="flex items-center justify-between text-muted-foreground">
                    <div className="flex items-center gap-1 font-medium text-foreground">
                      <span>{fromName}</span>
                      <ArrowRight className="w-3 h-3 text-primary shrink-0" />
                      <span className="text-primary">{toName}</span>
                    </div>
                    {timeStr && <span className="text-[10px] text-muted-foreground">{timeStr}</span>}
                  </div>
                  {rec.summary && (
                    <p className="text-muted-foreground text-[11px] bg-muted/20 p-1.5 rounded line-clamp-3">
                      {rec.summary}
                    </p>
                  )}
                  {Array.isArray(rec.changed_files) && rec.changed_files.length > 0 && (
                    <div className="flex flex-wrap gap-1 pt-0.5">
                      {rec.changed_files.map((file, fIdx) => (
                        <span
                          key={fIdx}
                          className="px-1.5 py-0.5 rounded text-[9px] font-mono bg-muted text-muted-foreground truncate max-w-[200px]"
                          title={file}
                        >
                          {file}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}
