'use client';

import { useCallback, useEffect, useState } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import type { KanbanTask } from '@/services/kanban';
import {
  raceDecide,
  raceEstimate,
  raceLaneChanges,
  raceLaneFile,
  raceLanes,
  raceStart,
  type RaceEstimate,
  type RaceLane,
  type RaceLaneFile,
} from '@/services/kanban';
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

const ERROR_KEY_BY_CODE: Record<string, string> = {
  race_requires_branch: 'raceNeedsBranch',
  bad_lane_count: 'raceErrorBadCount',
  insufficient_slots: 'raceErrorSlots',
  race_in_progress: 'raceErrorInProgress',
  cost_confirmation_required: 'raceErrorConfirm',
  winner_not_reviewable: 'raceErrorReviewable',
  race_parent_not_ready: 'raceErrorParentReady',
};

function raceErrorKey(err: unknown): string {
  const code = (err as { businessCode?: unknown }).businessCode;
  if (typeof code === 'string' && ERROR_KEY_BY_CODE[code]) {
    return ERROR_KEY_BY_CODE[code];
  }
  return 'raceErrorGeneric';
}

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

function languageForPath(path: string): string {
  const ext = path.split('.').pop()?.toLowerCase() ?? '';
  if (['ts', 'tsx', 'js', 'jsx', 'py', 'go', 'rs', 'java', 'json', 'yaml', 'yml', 'md', 'css', 'html'].includes(ext)) {
    return ext === 'tsx' || ext === 'jsx' ? 'typescript' : ext;
  }
  return 'plaintext';
}

function LaneCompare({
  boardId,
  parentTaskId,
  lane,
  t,
}: {
  boardId: string;
  parentTaskId: string;
  lane: RaceLane;
  t: (key: string, values?: Record<string, string | number>) => string;
}) {
  const [open, setOpen] = useState(false);
  const [files, setFiles] = useState<{ path: string; additions: number; deletions: number }[] | null>(null);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [file, setFile] = useState<RaceLaneFile | null>(null);
  const [DiffView, setDiffView] = useState<React.ComponentType<{
    currentContent: string;
    versions: { versionId: string; versionNumber: number; content: string; createdAt: string }[];
    viewingVersionIndex: number;
    language?: string;
  }> | null>(null);

  useEffect(() => {
    if (!open || files !== null) {
      return;
    }
    let cancelled = false;
    Promise.resolve(raceLaneChanges(boardId, parentTaskId, lane.task_id))
      .then((res) => {
        if (!cancelled) {
          setFiles(res.files);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setFiles([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [open, files, boardId, parentTaskId, lane.task_id]);

  const handleSelectFile = async (path: string) => {
    setSelectedPath(path);
    setFile(null);
    try {
      const res = await Promise.resolve(raceLaneFile(boardId, parentTaskId, lane.task_id, path));
      setFile(res);
      if (!DiffView) {
        const mod = await import('@/components/features/artifacts/renderers/DiffPreview');
        setDiffView(() => mod.default);
      }
    } catch {
      setFile(null);
    }
  };

  return (
    <details className="mt-1.5" onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary className="text-[11px] text-primary cursor-pointer">{t('raceChanges')}</summary>
      {open && files === null && <p className="text-[11px] text-muted-foreground mt-1">{t('loading')}</p>}
      {open && files !== null && files.length === 0 && (
        <p className="text-[11px] text-muted-foreground mt-1">{t('raceChangesEmpty')}</p>
      )}
      {open && files !== null && files.length > 0 && (
        <div className="mt-1 space-y-1">
          {files.map((f) => (
            <button
              key={f.path}
              type="button"
              onClick={() => handleSelectFile(f.path)}
              className={cn(
                'block w-full text-left text-[11px] px-2 py-1 rounded-md border border-border truncate',
                selectedPath === f.path ? 'bg-primary/10 border-primary' : '',
              )}
            >
              <span className="text-green-600 dark:text-green-400">+{f.additions}</span>{' '}
              <span className="text-red-600 dark:text-red-400">-{f.deletions}</span>{' '}
              <span className="font-mono">{f.path}</span>
            </button>
          ))}
          {selectedPath && file && DiffView && (
            <div className="h-72 mt-1">
              <DiffView
                currentContent={file.lane_content}
                versions={[
                  { versionId: 'target', versionNumber: 1, content: file.target_content, createdAt: '' },
                  { versionId: 'lane', versionNumber: 2, content: file.lane_content, createdAt: '' },
                ]}
                viewingVersionIndex={-1}
                language={languageForPath(file.path)}
              />
            </div>
          )}
        </div>
      )}
    </details>
  );
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
      const res = await Promise.resolve(raceLanes(boardId, task.task_id));
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

  const hasLiveLanes =
    lanes !== null &&
    lanes.some((lane) => lane.status === 'ready' || lane.status === 'running' || lane.status === 'blocked');

  useEffect(() => {
    const onEvent = (e: Event) => {
      const detail = (e as CustomEvent).detail as { board_id?: string } | undefined;
      if (!detail?.board_id || detail.board_id === boardId) {
        load();
      }
    };
    window.addEventListener('kanban-task-updated', onEvent);
    return () => window.removeEventListener('kanban-task-updated', onEvent);
  }, [boardId, load]);

  useEffect(() => {
    if (!hasLiveLanes) {
      return;
    }
    const interval = setInterval(load, 8000);
    return () => clearInterval(interval);
  }, [hasLiveLanes, load]);

  useEffect(() => {
    if (lanes !== null && lanes.length > 0) {
      return;
    }
    let cancelled = false;
    Promise.resolve(raceEstimate(boardId, task.task_id, laneCount))
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
      setError(raceErrorKey(err));
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
      setError(raceErrorKey(err));
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
              <LaneCompare boardId={boardId} parentTaskId={task.task_id} lane={lane} t={t} />
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
