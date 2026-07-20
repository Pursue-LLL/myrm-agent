'use client';

import { cn } from '@/lib/utils/classnameUtils';
import type { KanbanTask } from '@/services/kanban';
import { PRIORITY_STYLES, TIMEOUT_PRESETS, formatDate, formatDuration } from './kanban-styles';
import KanbanMarkdown from './KanbanMarkdown';
import { Clock, ExternalLink, User } from 'lucide-react';
import Link from 'next/link';
import type { Agent } from '@/services/agent';
import { KANBAN_SOURCE_CHAT_METADATA_KEY } from '@/services/kanban';
import { buildKanbanBoardDeepLink } from '@/lib/kanban/kanbanChatBoard';

interface TaskDetailsSectionProps {
  task: KanbanTask;
  agentName: string | null;
  progressPill: { done: number; total: number } | null;
  editingTimeout: boolean;
  setEditingTimeout: (v: boolean) => void;
  timeoutValue: number | null;
  setTimeoutValue: (v: number | null) => void;
  handleSaveTimeout: (v: number | null) => void;
  editingSkills: boolean;
  setEditingSkills: (v: boolean) => void;
  skillsText: string;
  setSkillsText: (v: string) => void;
  handleSaveSkills: () => void;
  editingCriteria: boolean;
  setEditingCriteria: (v: boolean) => void;
  criteriaText: string;
  setCriteriaText: (v: string) => void;
  savingCriteria: boolean;
  handleSaveCriteria: () => void;
  assignedAgent: Agent | null;
  agents: Agent[];
  handleAgentChange: (agentId: string | null) => void;
  t: (key: string) => string;
}

export function TaskDetailsSection({
  task,
  agentName,
  progressPill,
  editingTimeout,
  setEditingTimeout,
  timeoutValue,
  setTimeoutValue,
  handleSaveTimeout,
  editingSkills,
  setEditingSkills,
  skillsText,
  setSkillsText,
  handleSaveSkills,
  editingCriteria,
  setEditingCriteria,
  criteriaText,
  setCriteriaText,
  savingCriteria,
  handleSaveCriteria,
  assignedAgent,
  agents,
  handleAgentChange,
  t,
}: TaskDetailsSectionProps) {
  const sourceChatId =
    typeof task.metadata?.[KANBAN_SOURCE_CHAT_METADATA_KEY] === 'string'
      ? task.metadata[KANBAN_SOURCE_CHAT_METADATA_KEY]
      : null;

  return (
    <div className="space-y-1.5">
      {task.description && <KanbanMarkdown className="text-muted-foreground">{task.description}</KanbanMarkdown>}
      <div className="flex items-center gap-2 flex-wrap text-[10px]">
        <span className={cn('px-1.5 py-0.5 rounded-full border font-medium', PRIORITY_STYLES[task.priority])}>
          {task.priority}
        </span>
        <span className="text-muted-foreground">{t(`status.${task.status}`)}</span>
        {task.agent_id && agentName && (
          <span
            className="px-1.5 py-0.5 rounded-full bg-chart-4/10 text-chart-4 border border-chart-4/20 truncate max-w-[120px]"
            title={agentName}
          >
            {agentName}
          </span>
        )}
        {progressPill && (
          <span
            className={cn(
              'px-1.5 py-0.5 rounded-full border',
              progressPill.done === progressPill.total
                ? 'bg-chart-2/10 text-chart-2 border-chart-2/20'
                : 'bg-primary/10 text-primary border-primary/20',
            )}
          >
            {progressPill.done}/{progressPill.total}
          </span>
        )}
      </div>
      <div className="flex gap-3 text-[10px] text-muted-foreground/70 mt-1 flex-wrap items-center">
        <span>
          {t('createdAt')}: {formatDate(task.created_at)}
        </span>
        <span>
          {t('updatedAt')}: {formatDate(task.updated_at)}
        </span>
        {sourceChatId && (
          <>
            <Link
              href={`/${sourceChatId}`}
              className="inline-flex items-center gap-0.5 text-primary hover:underline"
            >
              {t('openSourceChat')}
              <ExternalLink className="w-3 h-3" />
            </Link>
            <Link
              href={buildKanbanBoardDeepLink({ sourceChatId: sourceChatId, boardId: task.board_id })}
              className="inline-flex items-center gap-0.5 text-primary hover:underline"
            >
              {t('viewBoardTasksFromChat')}
              <ExternalLink className="w-3 h-3" />
            </Link>
          </>
        )}
      </div>

      {/* Timeout */}
      {editingTimeout ? (
        <div className="mt-1 rounded border border-chart-5/30 bg-chart-5/5 px-2 py-1.5 space-y-1">
          <span className="text-[10px] font-semibold text-chart-5 uppercase tracking-wider">
            {t('timeoutLabel')}
          </span>
          <select
            value={timeoutValue === null ? '' : String(timeoutValue)}
            onChange={(e) => setTimeoutValue(e.target.value ? Number(e.target.value) : null)}
            className="w-full text-xs px-2 py-1 rounded border bg-background focus:outline-none focus:ring-1 focus:ring-chart-5"
            autoFocus
          >
            <option value="">{t('timeoutDefault')}</option>
            {TIMEOUT_PRESETS.map((p) => (
              <option key={p.value} value={p.value}>
                {t(p.labelKey)}
              </option>
            ))}
          </select>
          <div className="flex gap-1">
            <button
              onClick={() => handleSaveTimeout(timeoutValue)}
              className="text-[10px] px-2 py-0.5 rounded bg-chart-5 text-white hover:bg-chart-5/80"
            >
              {t('save')}
            </button>
            <button
              onClick={() => setEditingTimeout(false)}
              className="text-[10px] px-2 py-0.5 rounded hover:bg-muted"
            >
              {t('cancel')}
            </button>
          </div>
        </div>
      ) : task.max_runtime_seconds != null ? (
        <span
          className="inline-flex text-[10px] px-1.5 py-0.5 rounded-full bg-chart-5/10 text-chart-5 border border-chart-5/20 mt-1 cursor-pointer hover:border-chart-5/40 transition-colors"
          onClick={() => {
            setTimeoutValue(task.max_runtime_seconds ?? null);
            setEditingTimeout(true);
          }}
        >
          {t('timeoutLabel')}: {formatDuration(task.max_runtime_seconds)}
        </span>
      ) : (
        <button
          onClick={() => {
            setTimeoutValue(null);
            setEditingTimeout(true);
          }}
          className="text-[10px] text-muted-foreground hover:text-chart-5 transition-colors mt-1"
        >
          + {t('timeoutLabel')}
        </button>
      )}

      {/* Skills */}
      {editingSkills ? (
        <div className="mt-1 rounded border border-chart-3/30 bg-chart-3/5 px-2 py-1.5 space-y-1">
          <span className="text-[10px] font-semibold text-chart-3 uppercase tracking-wider">
            {t('skillsLabel')}
          </span>
          <input
            value={skillsText}
            onChange={(e) => setSkillsText(e.target.value)}
            placeholder={t('skillsPlaceholder')}
            className="w-full text-xs px-2 py-1 rounded border bg-background focus:outline-none focus:ring-1 focus:ring-chart-3"
            autoFocus
            onKeyDown={(e) => e.key === 'Enter' && handleSaveSkills()}
          />
          <div className="flex gap-1">
            <button
              onClick={handleSaveSkills}
              className="text-[10px] px-2 py-0.5 rounded bg-chart-3 text-white hover:bg-chart-3/80"
            >
              {t('save')}
            </button>
            <button
              onClick={() => setEditingSkills(false)}
              className="text-[10px] px-2 py-0.5 rounded hover:bg-muted"
            >
              {t('cancel')}
            </button>
          </div>
        </div>
      ) : task.extra_skill_ids && task.extra_skill_ids.length > 0 ? (
        <div
          className="flex flex-wrap gap-1 mt-1 cursor-pointer group/skills"
          onClick={() => {
            setSkillsText(task.extra_skill_ids.join(', '));
            setEditingSkills(true);
          }}
        >
          {task.extra_skill_ids.map((sid) => (
            <span
              key={sid}
              className="inline-flex text-[10px] px-1.5 py-0.5 rounded-full bg-chart-3/10 text-chart-3 border border-chart-3/20 group-hover/skills:border-chart-3/40 transition-colors"
            >
              {sid}
            </span>
          ))}
        </div>
      ) : (
        <button
          onClick={() => {
            setSkillsText('');
            setEditingSkills(true);
          }}
          className="text-[10px] text-muted-foreground hover:text-chart-3 transition-colors mt-1"
        >
          + {t('skillsLabel')}
        </button>
      )}

      {/* Progress note & blocked */}
      {task.status === 'running' && task.progress_note && (
        <p className="text-xs text-chart-4 bg-chart-4/5 rounded px-2 py-1 mt-1 font-medium">{task.progress_note}</p>
      )}
      {task.blocked_reason && (
        <div className="text-xs text-destructive bg-destructive/5 rounded px-2 py-1 mt-1 space-y-0.5">
          <p className="flex items-center gap-1">
            {task.block_kind === 'scheduled' && <Clock className="w-3.5 h-3.5 shrink-0" />}
            {task.block_kind === 'external' && <ExternalLink className="w-3.5 h-3.5 shrink-0" />}
            {task.block_kind === 'human' && <User className="w-3.5 h-3.5 shrink-0" />}
            <span className="font-medium capitalize">{task.block_kind ?? 'blocked'}</span>
            <span className="text-muted-foreground">—</span>
            {task.blocked_reason}
          </p>
          {task.block_kind === 'scheduled' && task.scheduled_until && (
            <p className="text-[10px] text-chart-4 font-mono">
              {t('autoUnblockAt')}: {new Date(task.scheduled_until).toLocaleString()}
            </p>
          )}
        </div>
      )}

      {/* Completion criteria */}
      <div className="mt-1.5">
        {editingCriteria ? (
          <div className="rounded border border-primary/30 bg-primary/5 px-2 py-1.5 space-y-1.5">
            <span className="text-[10px] font-semibold text-primary uppercase tracking-wider">
              {t('completionCriteria')}
            </span>
            <textarea
              value={criteriaText}
              onChange={(e) => setCriteriaText(e.target.value)}
              placeholder={t('criteriaPlaceholder')}
              className="w-full text-xs px-2 py-1.5 rounded border bg-background focus:outline-none focus:ring-1 focus:ring-primary resize-none"
              rows={3}
              autoFocus
            />
            <div className="flex gap-1.5">
              <button
                onClick={handleSaveCriteria}
                disabled={savingCriteria}
                className="text-[10px] px-2 py-0.5 rounded bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >
                {t('send')}
              </button>
              <button
                onClick={() => setEditingCriteria(false)}
                className="text-[10px] px-2 py-0.5 rounded hover:bg-muted"
              >
                {t('cancel')}
              </button>
            </div>
          </div>
        ) : task.completion_criteria ? (
          <div
            className="rounded border border-primary/20 bg-primary/5 px-2 py-1.5 cursor-pointer hover:border-primary/40 transition-colors group/criteria"
            onClick={() => {
              setCriteriaText(task.completion_criteria ?? '');
              setEditingCriteria(true);
            }}
          >
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-semibold text-primary uppercase tracking-wider">
                {t('completionCriteria')}
              </span>
              <span className="text-[9px] text-primary/50 opacity-0 group-hover/criteria:opacity-100 transition-opacity">
                {t('editCriteria')}
              </span>
            </div>
            <KanbanMarkdown className="text-foreground/80 mt-0.5">{task.completion_criteria}</KanbanMarkdown>
          </div>
        ) : (
          <button
            onClick={() => {
              setCriteriaText('');
              setEditingCriteria(true);
            }}
            className="text-[10px] text-primary/60 hover:text-primary transition-colors"
          >
            + {t('completionCriteria')}
          </button>
        )}
      </div>

      {/* Agent assignment */}
      {agents.length > 0 && (
        <div className="flex items-center gap-2 mt-1.5">
          <span className="text-[10px] text-muted-foreground font-medium shrink-0">{t('assignedAgent')}:</span>
          {assignedAgent?.avatar_url ? (
            <img
              src={assignedAgent.avatar_url}
              alt={assignedAgent.name}
              className="w-4 h-4 rounded-full shrink-0 object-cover"
            />
          ) : task.agent_id && agentName ? (
            <span className="w-4 h-4 rounded-full shrink-0 bg-chart-4/20 text-chart-4 text-[8px] font-bold flex items-center justify-center">
              {agentName.charAt(0).toUpperCase()}
            </span>
          ) : null}
          <select
            value={task.agent_id ?? ''}
            onChange={(e) => handleAgentChange(e.target.value || null)}
            className="text-[10px] px-1.5 py-0.5 rounded border bg-background focus:outline-none focus:ring-1 focus:ring-primary max-w-[140px]"
          >
            <option value="">{t('unassigned')}</option>
            {agents.map((ag) => (
              <option key={ag.id} value={ag.id}>
                {ag.name}
              </option>
            ))}
          </select>
        </div>
      )}
    </div>
  );
}
