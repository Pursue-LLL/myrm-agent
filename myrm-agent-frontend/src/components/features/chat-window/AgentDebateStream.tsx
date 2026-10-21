'use client';

/**
 * [INPUT]: room (DebateRoomStateData), onAdvancePhase, onAdoptConsensus, onSyncKanban, onDismiss, className
 * [OUTPUT]: AgentDebateStream 折叠式多智能体协同辩论流、Leader 任务拆解与 Kanban 看板状态联动面板
 * [POS]: myrm-agent-frontend/src/components/features/chat-window/AgentDebateStream.tsx
 */

import React, { useState } from 'react';
import {
  Users,
  ChevronDown,
  ChevronUp,
  Gavel,
  ShieldAlert,
  ArrowRight,
  Kanban,
  CheckCircle2,
  Sparkles,
  Layers,
  X,
  Clock,
} from 'lucide-react';

export type DebateRole = 'leader' | 'researcher' | 'critic' | 'implementer' | 'synthesizer';

export type DebatePhase =
  | 'decomposition'
  | 'round_argument'
  | 'cross_examination'
  | 'convergence'
  | 'settled';

export type DebateSubtaskStatus = 'todo' | 'in_progress' | 'blocked' | 'in_review' | 'done';

export interface DebateParticipantItem {
  agentId: string;
  name: string;
  role: DebateRole;
  model?: string | null;
}

export interface DebateSubtaskItem {
  taskId: string;
  title: string;
  description: string;
  assignedAgentId: string;
  assignedRole: DebateRole;
  status: DebateSubtaskStatus;
  kanbanTaskId?: string | null;
}

export interface DebateTurnItem {
  turnId: string;
  speakerId: string;
  speakerName: string;
  role: DebateRole;
  phase: DebatePhase;
  roundIndex: intOrNumber;
  thesis: string;
  counterPoints: string[];
  evidence: string[];
  confidence: number;
  kanbanTaskId?: string | null;
  createdAt?: number;
}

type intOrNumber = number;

export interface DebateRoomStateData {
  roomId: string;
  chatId: string;
  topic: string;
  leaderAgentId: string;
  phase: DebatePhase;
  roundIndex: number;
  maxRounds: number;
  participants: DebateParticipantItem[];
  subtasks: DebateSubtaskItem[];
  turns: DebateTurnItem[];
  consensusDecision?: string | null;
  kanbanBoardId?: string | null;
}

export interface AgentDebateStreamProps {
  room: DebateRoomStateData;
  onAdvancePhase?: (roomId: string) => void;
  onAdoptConsensus?: (roomId: string, decision: string) => void;
  onSyncKanban?: (roomId: string, taskId: string, kanbanTaskId: string) => void;
  onDismiss?: () => void;
  className?: string;
}

const ROLE_COLORS: Record<DebateRole, { badge: string; text: string }> = {
  leader: { badge: 'bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/20', text: 'Leader' },
  researcher: { badge: 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20', text: 'Researcher' },
  critic: { badge: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20', text: 'Critic' },
  implementer: { badge: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20', text: 'Implementer' },
  synthesizer: { badge: 'bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border-indigo-500/20', text: 'Synthesizer' },
};

const PHASE_CONFIG: Record<DebatePhase, { label: string; color: string }> = {
  decomposition: { label: 'Task Decomposition', color: 'bg-sky-500/10 text-sky-600 dark:text-sky-400 border-sky-500/20' },
  round_argument: { label: 'Specialist Argument', color: 'bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border-indigo-500/20' },
  cross_examination: { label: 'Cross-Examination', color: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20' },
  convergence: { label: 'Consensus Convergence', color: 'bg-fuchsia-500/10 text-fuchsia-600 dark:text-fuchsia-400 border-fuchsia-500/20' },
  settled: { label: 'Decision Settled', color: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20' },
};

const SUBTASK_STATUS_COLORS: Record<DebateSubtaskStatus, string> = {
  todo: 'bg-neutral-500/10 text-neutral-600 dark:text-neutral-400 border-neutral-500/20',
  in_progress: 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20',
  blocked: 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20',
  in_review: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20',
  done: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20',
};

export const AgentDebateStream: React.FC<AgentDebateStreamProps> = ({
  room,
  onAdvancePhase,
  onAdoptConsensus,
  onSyncKanban,
  onDismiss,
  className = '',
}) => {
  const [isExpanded, setIsExpanded] = useState<boolean>(true);
  const [activeTab, setActiveTab] = useState<'turns' | 'subtasks'>('turns');

  const phaseMeta = PHASE_CONFIG[room.phase] || PHASE_CONFIG.round_argument;
  const isAntiWheelWarActive = room.roundIndex >= room.maxRounds && room.phase !== 'settled';

  return (
    <section
      aria-label="Multi-Agent Debate Workroom"
      className={`rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white/95 dark:bg-neutral-900/95 backdrop-blur-md shadow-lg overflow-hidden transition-all duration-300 ${className}`}
    >
      {/* Top Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-neutral-50/80 dark:bg-neutral-800/50 border-b border-neutral-200/80 dark:border-neutral-700/80">
        <div className="flex items-center gap-2 min-w-0">
          <div className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-600 dark:text-indigo-400">
            <Users className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-sm text-neutral-900 dark:text-neutral-100 truncate">
                {room.topic}
              </span>
              <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full border ${phaseMeta.color}`}>
                {phaseMeta.label}
              </span>
              <span className="text-[10px] text-neutral-500 dark:text-neutral-400 font-mono">
                Round {room.roundIndex}/{room.maxRounds}
              </span>
            </div>
            <div className="flex items-center gap-2 text-[11px] text-neutral-500 dark:text-neutral-400">
              <span>Room: {room.roomId}</span>
              <span>•</span>
              <span>{room.participants.length} Agents</span>
              {room.kanbanBoardId && (
                <>
                  <span>•</span>
                  <span className="inline-flex items-center gap-1 text-sky-600 dark:text-sky-400">
                    <Kanban className="w-3 h-3" />
                    Board: {room.kanbanBoardId}
                  </span>
                </>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1.5 ml-2 shrink-0">
          <button
            type="button"
            aria-label={isExpanded ? 'Collapse Debate Stream' : 'Expand Debate Stream'}
            onClick={() => setIsExpanded(!isExpanded)}
            className="p-1.5 rounded-md hover:bg-neutral-200/60 dark:hover:bg-neutral-700/60 text-neutral-500 dark:text-neutral-400 transition-colors"
          >
            {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
          {onDismiss && (
            <button
              type="button"
              aria-label="Close Debate Panel"
              onClick={onDismiss}
              className="p-1.5 rounded-md hover:bg-neutral-200/60 dark:hover:bg-neutral-700/60 text-neutral-500 dark:text-neutral-400 transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Anti-Wheel-War Warning Guard */}
      {isAntiWheelWarActive && (
        <div className="flex items-center gap-2 px-4 py-2 bg-amber-50 dark:bg-amber-950/40 border-b border-amber-200/60 dark:border-amber-800/60 text-amber-800 dark:text-amber-200 text-xs">
          <ShieldAlert className="w-4 h-4 shrink-0 text-amber-600 dark:text-amber-400" />
          <span>
            Anti-Wheel-War Limit Reached: Max {room.maxRounds} debate rounds consumed. Forced consensus convergence activated.
          </span>
        </div>
      )}

      {isExpanded && (
        <div className="p-4 space-y-4">
          {/* Subtasks vs Turns Tab Switcher */}
          <div className="flex items-center gap-2 border-b border-neutral-200 dark:border-neutral-800 pb-2">
            <button
              type="button"
              onClick={() => setActiveTab('turns')}
              className={`flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-md transition-colors ${
                activeTab === 'turns'
                  ? 'bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900'
                  : 'text-neutral-600 dark:text-neutral-400 hover:bg-neutral-100 dark:hover:bg-neutral-800'
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              Debate Turns ({room.turns.length})
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('subtasks')}
              className={`flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-md transition-colors ${
                activeTab === 'subtasks'
                  ? 'bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900'
                  : 'text-neutral-600 dark:text-neutral-400 hover:bg-neutral-100 dark:hover:bg-neutral-800'
              }`}
            >
              <Kanban className="w-3.5 h-3.5" />
              Decomposed Subtasks ({room.subtasks.length})
            </button>
          </div>

          {/* Active Tab: Turns */}
          {activeTab === 'turns' && (
            <div className="space-y-3 max-h-72 overflow-y-auto pr-1">
              {room.turns.length === 0 ? (
                <div className="py-6 text-center text-xs text-neutral-400 dark:text-neutral-500">
                  No debate arguments posted yet. Leader is organizing the discussion.
                </div>
              ) : (
                room.turns.map((turn) => {
                  const roleStyle = ROLE_COLORS[turn.role] || ROLE_COLORS.researcher;
                  return (
                    <div
                      key={turn.turnId}
                      className="p-3 rounded-lg border border-neutral-100 dark:border-neutral-800/80 bg-neutral-50/50 dark:bg-neutral-800/30 space-y-2 text-xs"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-neutral-900 dark:text-neutral-100">
                            {turn.speakerName}
                          </span>
                          <span className={`text-[10px] px-1.5 py-0.5 rounded border ${roleStyle.badge}`}>
                            {roleStyle.text}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 text-[10px] text-neutral-400 font-mono">
                          <span>Conf: {(turn.confidence * 100).toFixed(0)}%</span>
                          <span>•</span>
                          <span>Round {turn.roundIndex}</span>
                        </div>
                      </div>

                      {/* Thesis */}
                      <p className="text-neutral-800 dark:text-neutral-200 leading-relaxed font-normal">
                        {turn.thesis}
                      </p>

                      {/* Counter Points */}
                      {turn.counterPoints.length > 0 && (
                        <div className="space-y-1 pt-1 border-t border-neutral-200/50 dark:border-neutral-700/50">
                          <span className="text-[10px] font-semibold text-rose-600 dark:text-rose-400 uppercase tracking-wider">
                            Counter-Points / Critiques:
                          </span>
                          <ul className="list-disc list-inside text-[11px] text-neutral-600 dark:text-neutral-300 space-y-0.5">
                            {turn.counterPoints.map((cp, idx) => (
                              <li key={idx}>{cp}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {/* Evidence */}
                      {turn.evidence.length > 0 && (
                        <div className="space-y-1">
                          <span className="text-[10px] font-semibold text-sky-600 dark:text-sky-400 uppercase tracking-wider">
                            Supporting Evidence:
                          </span>
                          <div className="flex flex-wrap gap-1">
                            {turn.evidence.map((ev, idx) => (
                              <span
                                key={idx}
                                className="inline-block px-1.5 py-0.5 rounded bg-sky-50 dark:bg-sky-950/40 text-sky-700 dark:text-sky-300 text-[10px] font-mono border border-sky-200 dark:border-sky-800/40"
                              >
                                {ev}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          )}

          {/* Active Tab: Subtasks */}
          {activeTab === 'subtasks' && (
            <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
              {room.subtasks.length === 0 ? (
                <div className="py-6 text-center text-xs text-neutral-400 dark:text-neutral-500">
                  No subtasks decomposed yet.
                </div>
              ) : (
                room.subtasks.map((st) => {
                  const statusStyle = SUBTASK_STATUS_COLORS[st.status] || SUBTASK_STATUS_COLORS.todo;
                  const roleStyle = ROLE_COLORS[st.assignedRole] || ROLE_COLORS.implementer;
                  return (
                    <div
                      key={st.taskId}
                      className="flex items-start justify-between p-2.5 rounded-lg border border-neutral-100 dark:border-neutral-800 bg-neutral-50/40 dark:bg-neutral-800/20 text-xs gap-3"
                    >
                      <div className="min-w-0 space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-neutral-900 dark:text-neutral-100 truncate">
                            {st.title}
                          </span>
                          <span className={`text-[10px] px-1.5 py-0.5 rounded border ${roleStyle.badge}`}>
                            {roleStyle.text}
                          </span>
                        </div>
                        <p className="text-[11px] text-neutral-500 dark:text-neutral-400">
                          {st.description}
                        </p>
                      </div>

                      <div className="flex items-center gap-2 shrink-0">
                        <span className={`text-[10px] px-2 py-0.5 rounded-full border uppercase font-mono font-medium ${statusStyle}`}>
                          {st.status}
                        </span>
                        {st.kanbanTaskId ? (
                          <span className="text-[10px] text-sky-600 dark:text-sky-400 font-mono">
                            #{st.kanbanTaskId.replace(/^kb-/, '')}
                          </span>
                        ) : (
                          onSyncKanban && (
                            <button
                              type="button"
                              onClick={() => onSyncKanban(room.roomId, st.taskId, `kanban-${st.taskId}`)}
                              className="text-[10px] px-2 py-1 rounded bg-sky-50 dark:bg-sky-950/40 text-sky-600 dark:text-sky-400 border border-sky-300 dark:border-sky-800 hover:bg-sky-100 dark:hover:bg-sky-900/60 transition-colors"
                            >
                              Sync Kanban
                            </button>
                          )
                        )}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          )}

          {/* Consensus Decision Settled Block */}
          {room.consensusDecision && (
            <div className="p-3 rounded-lg border border-emerald-200 dark:border-emerald-800/60 bg-emerald-50/60 dark:bg-emerald-950/30 space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-emerald-800 dark:text-emerald-200">
                  <Gavel className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                  <span>Consensus Decision Adopted</span>
                </div>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-700 dark:text-emerald-300 border border-emerald-500/30 font-medium">
                  Settled
                </span>
              </div>
              <p className="text-xs text-emerald-900 dark:text-emerald-100 leading-relaxed font-medium">
                {room.consensusDecision}
              </p>
              {onAdoptConsensus && room.phase !== 'settled' && (
                <button
                  type="button"
                  onClick={() => onAdoptConsensus(room.roomId, room.consensusDecision || '')}
                  className="mt-2 inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm transition-colors"
                >
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  Confirm & Sync Kanban Tasks
                </button>
              )}
            </div>
          )}

          {/* Action Bar */}
          <div className="flex items-center justify-between pt-2 border-t border-neutral-200/80 dark:border-neutral-800/80 text-xs">
            <span className="text-neutral-500 dark:text-neutral-400 flex items-center gap-1">
              <Clock className="w-3.5 h-3.5" />
              Leader: {room.leaderAgentId}
            </span>
            {onAdvancePhase && room.phase !== 'settled' && (
              <button
                type="button"
                onClick={() => onAdvancePhase(room.roomId)}
                className="inline-flex items-center gap-1 text-xs font-medium px-3 py-1.5 rounded-lg bg-neutral-900 hover:bg-neutral-800 dark:bg-neutral-100 dark:hover:bg-white text-white dark:text-neutral-900 transition-colors"
              >
                <span>Advance Phase</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>
      )}
    </section>
  );
};

export default AgentDebateStream;
