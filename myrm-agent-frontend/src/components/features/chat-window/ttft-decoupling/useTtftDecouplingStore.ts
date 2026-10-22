import { create } from 'zustand';
import {
  DagStepNode,
  DagStepStatus,
  DagTimelineState,
  EmitEarlyAckParams,
  InitDagTimelineParams,
  SpeculativeAckPayload,
  SpeculativeAckStatus,
} from './ttftDecouplingTypes';

interface TtftDecouplingState {
  activeAcks: Record<string, SpeculativeAckPayload>;
  activeDags: Record<string, DagTimelineState>;
  isTimelineExpanded: Record<string, boolean>;

  emitEarlyAck: (params: EmitEarlyAckParams) => string;
  updateAckStatus: (ackId: string, status: SpeculativeAckStatus) => void;
  initDagTimeline: (params: InitDagTimelineParams) => void;
  updateDagStepStatus: (
    dagId: string,
    stepId: string,
    status: DagStepStatus,
    elapsedMs?: number,
  ) => void;
  toggleTimelineExpansion: (dagId: string, expanded?: boolean) => void;
  dismissAck: (ackId: string) => void;
  reset: () => void;
}

let ackSeq = 0;

export const useTtftDecouplingStore = create<TtftDecouplingState>((set) => ({
  activeAcks: {},
  activeDags: {},
  isTimelineExpanded: {},

  emitEarlyAck: (params: EmitEarlyAckParams): string => {
    ackSeq += 1;
    const id = params.id ?? `ack-${Date.now()}-${ackSeq}`;
    const ackTimestamp = params.ackTimestamp ?? Date.now() - 140;

    const payload: SpeculativeAckPayload = {
      id,
      messageId: params.messageId,
      status: 'intent_analyzed',
      intentSummary:
        params.intentSummary ?? '已即时接收意图，正在检索上下文并编排关键链路...',
      speculativeTools: params.tools ?? ['vector_search', 'code_interpreter'],
      ackTimestamp,
      elapsedMs: 140,
    };

    set((state) => ({
      activeAcks: {
        ...state.activeAcks,
        [id]: payload,
      },
    }));

    return id;
  },

  updateAckStatus: (ackId: string, status: SpeculativeAckStatus): void => {
    set((state) => {
      const existing = state.activeAcks[ackId];
      if (!existing) {
        return state;
      }

      return {
        activeAcks: {
          ...state.activeAcks,
          [ackId]: {
            ...existing,
            status,
          },
        },
      };
    });
  },

  initDagTimeline: (params: InitDagTimelineParams): void => {
    const nodes: DagStepNode[] = params.steps.map((s) => ({
      id: s.id,
      name: s.name,
      description: s.description,
      status: 'pending',
      parallelGroupId: s.parallelGroupId,
      isCriticalPath: s.isCriticalPath ?? true,
    }));

    const timeline: DagTimelineState = {
      dagId: params.dagId,
      messageId: params.messageId,
      totalSteps: nodes.length,
      completedSteps: 0,
      isAllCompleted: false,
      steps: nodes,
      startedAt: Date.now(),
    };

    set((state) => ({
      activeDags: {
        ...state.activeDags,
        [params.dagId]: timeline,
      },
      isTimelineExpanded: {
        ...state.isTimelineExpanded,
        [params.dagId]: true,
      },
    }));
  },

  updateDagStepStatus: (
    dagId: string,
    stepId: string,
    status: DagStepStatus,
    elapsedMs?: number,
  ): void => {
    set((state) => {
      const dag = state.activeDags[dagId];
      if (!dag) {
        return state;
      }

      const updatedSteps = dag.steps.map((s) => {
        if (s.id === stepId) {
          return {
            ...s,
            status,
            elapsedMs: elapsedMs !== undefined ? elapsedMs : s.elapsedMs,
          };
        }
        return s;
      });

      const completedCount = updatedSteps.filter(
        (s) => s.status === 'completed' || s.status === 'bypassed',
      ).length;

      const isAllCompleted = completedCount === updatedSteps.length;

      return {
        activeDags: {
          ...state.activeDags,
          [dagId]: {
            ...dag,
            steps: updatedSteps,
            completedSteps: completedCount,
            isAllCompleted,
            completedAt: isAllCompleted ? Date.now() : dag.completedAt,
          },
        },
      };
    });
  },

  toggleTimelineExpansion: (dagId: string, expanded?: boolean): void => {
    set((state) => ({
      isTimelineExpanded: {
        ...state.isTimelineExpanded,
        [dagId]:
          expanded !== undefined
            ? expanded
            : !state.isTimelineExpanded[dagId],
      },
    }));
  },

  dismissAck: (ackId: string): void => {
    set((state) => {
      const next = { ...state.activeAcks };
      delete next[ackId];
      return { activeAcks: next };
    });
  },

  reset: (): void => {
    set({
      activeAcks: {},
      activeDags: {},
      isTimelineExpanded: {},
    });
  },
}));
