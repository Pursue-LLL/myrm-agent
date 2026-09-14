'use client';

import { useCallback, useEffect, useState } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import type { KanbanTask } from '@/services/kanban';
import { raceDecide, raceEstimate, raceLanes, raceStart, type RaceEstimate, type RaceLane } from '@/services/kanban';
import useAgentStore from '@/store/useAgentStore';
import { getBuiltinAgentName } from '@/components/agent/builtin-agent-i18n';
import { useLocale } from 'next-intl';
import { STATUS_DOT } from './kanban-styles';

interface RaceSectionProps {
  boardId: string;
  task: KanbanTask;
  onChanged: () => void;
  t: (key: string, values?: Record<string, string | number>) => string;
}

const LETTERS = ['A', 'B', 'C', 'D', 'E'];

function LaneAgentName({ agentId }: { agentId: string | null | undefined }) {
  const locale = useLocale();
  const agents = useAgentStore((s) => s.agents);
  const fetchAgents = useAgentStore((s) => s.fetchAgents);
  useEffect(() => {
    if (agentId) {
      fetchAgents();
    }
  }, [agentId, fetchAgents]);
  if (!agentId) {
    return <span className="text-muted-foreground">—</span>;
  }
  const agent = agents.find((a) => a.id === agentId);
  return <span>{agent ? getBuiltinAgentName(agent.id, agent.name, locale) : agentId}</span>;
}

export default function RaceSection({ boardId, task, onChanged, t }: RaceSectionProps) {
  const [lanes, setLanes] = useState<RaceLane[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [laneCount, setLaneCount] = useState(3);
  const [variants, setVariants] = useState<string[]>(['', '', '', '', '']);
  const [estimate, setEstimate] = useState<RaceEstimate | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [starting, setStarting] = useState(false);
  const [deciding, setDeciding] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await raceLanes(boardId, task.task_id);
      setLanes(res.lanes);
    } catch {
      setLanes([]);
    } finally {
      setLoading(false);
    }
  }, [boardId, task.task_id]);

  useEffect(() => {
    setLanes(null);
    setEstimate(null);
    setConfirmed(false);
    setError(null);
    load();
  }, [load]);

  useEffect(() => {
    if (lanes !== null && lanes.length > 0) {
      return;
    }
    let cancelled = false;
    raceEstimate(boardId, task.task_id, laneCount)
      .then((est) => {
        if (!cancelled) {
          setEstimate(est);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setEstimate(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [boardId, task.task_id, laneCount, lanes]);

  const handleStart = async () => {
    if (!confirmed || starting) {
      return;
    }
    setStarting(true);
    setError(null);
    try {
      await raceStart(boardId, task.task_id, {
        lanes: Array.from({ length: laneCount }, (_, i) => ({
          instruction_variant: variants[i] || undefined,
        })),
        confirm_cost: true,
      });
      setConfirmed(false);
      await load();
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setStarting(false);
    }
  };

  const handleDecide = async (winnerId: string) => {
    if (deciding) {
      return;
    }
    setDeciding(winnerId);
    setError(null);
    try {
      await raceDecide(boardId, task.task_id, { winner_task_id: winnerId });
      await load();
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setDeciding(null);
    }
  };

  const decided =
    lanes !== null &&
    lanes.length > 0 &&
    lanes.every((lane) => lane.status === 'completed' || lane.status === 'archived');
  const canStart = Boolean(task.branch) && (task.status === 'backlog' || task.status === 'ready');

  return (
    <div className="px-4 py-3 border-b" data-testid="race-section">
      <h4 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{t('raceTitle')}</h4>

      {loading && <p className="text-xs text-muted-foreground mt-2">{t('loading')}</p>}
      {error && <p className="text-xs text-destructive mt-2">{error}</p>}

      {!loading && lanes !== null && lanes.length > 0 && (
        <div className="mt-2 space-y-2">
          {lanes.map((lane) => (
            <div key={lane.task_id} className="rounded-md border border-border p-2.5">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5 min-w-0">
                  <span
                    className={cn('w-2 h-2 rounded-full shrink-0', STATUS_DOT[lane.status] ?? 'bg-muted-foreground/50')}
                  />
                  <span className="text-xs font-medium truncate">{lane.title}</span>
                </div>
                <span className="text-[11px] text-muted-foreground shrink-0">
                  {lane.total_tokens > 0 ? t('raceTokens', { count: lane.total_tokens }) : ''}
                </span>
              </div>
              <div className="text-[11px] text-muted-foreground mt-1">
                <LaneAgentName agentId={lane.agent_id} />
                {lane.branch ? ` · ${lane.branch}` : ''}
              </div>
              {lane.result && (
                <details className="mt-1.5">
                  <summary className="text-[11px] text-primary cursor-pointer">{t('raceViewResult')}</summary>
                  <p className="text-xs whitespace-pre-wrap mt-1 max-h-40 overflow-y-auto">{lane.result}</p>
                </details>
              )}
              {lane.status === 'in_review' && !decided && (
                <button
                  type="button"
                  disabled={deciding !== null}
                  onClick={() => handleDecide(lane.task_id)}
                  className="mt-2 text-[11px] font-medium px-2.5 py-1 rounded-md bg-primary text-primary-foreground disabled:opacity-50"
                >
                  {deciding === lane.task_id ? t('raceDeciding') : t('racePickWinner')}
                </button>
              )}
            </div>
          ))}
          {decided && <p className="text-[11px] text-muted-foreground">{t('raceDecided')}</p>}
        </div>
      )}

      {!loading && lanes !== null && lanes.length === 0 && (
        <>
          {!canStart && <p className="text-xs text-muted-foreground mt-2">{t('raceNeedsBranch')}</p>}
          {canStart && (
            <div className="mt-2 space-y-2">
              <label className="flex items-center gap-2 text-xs">
                <span className="text-muted-foreground">{t('raceLaneCount')}</span>
                <select
                  value={laneCount}
                  onChange={(e) => setLaneCount(Number(e.target.value))}
                  className="bg-background border border-border rounded-md text-xs px-1.5 py-1"
                >
                  {[2, 3, 4, 5].map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
              </label>
              {Array.from({ length: laneCount }, (_, i) => (
                <input
                  key={i}
                  value={variants[i]}
                  onChange={(e) => {
                    const next = [...variants];
                    next[i] = e.target.value;
                    setVariants(next);
                  }}
                  placeholder={t('raceVariantPlaceholder', { letter: LETTERS[i] })}
                  className="w-full bg-background border border-border rounded-md text-xs px-2 py-1.5 placeholder:text-muted-foreground/60"
                />
              ))}
              {estimate && (
                <p className="text-[11px] text-muted-foreground">
                  {t('raceEstimate', {
                    total: estimate.total_tokens,
                    lanes: estimate.lanes,
                  })}
                </p>
              )}
              <label className="flex items-start gap-2 text-xs cursor-pointer">
                <input
                  type="checkbox"
                  checked={confirmed}
                  onChange={(e) => setConfirmed(e.target.checked)}
                  className="mt-0.5"
                />
                <span>{t('raceConfirmCost')}</span>
              </label>
              <button
                type="button"
                disabled={!confirmed || starting}
                onClick={handleStart}
                className="text-xs font-medium px-3 py-1.5 rounded-md bg-primary text-primary-foreground disabled:opacity-50"
              >
                {starting ? t('raceStarting') : t('raceStart')}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
