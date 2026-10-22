import { create } from 'zustand';
import {
  DEFAULT_BOOTSTRAP_PAYLOAD,
  DEFAULT_MOCK_CHANGES,
  validateConnectionEpoch,
} from './dockableWorkbenchEngine';
import type {
  BootstrapSessionPayload,
  DockablePanelId,
  DockPosition,
  FileChangeItem,
  TriSurfaceTaskState,
} from './dockableWorkbenchTypes';

export interface DockableWorkbenchState {
  readonly activePanelId: DockablePanelId | null;
  readonly dockPosition: DockPosition;
  readonly isCollapsed: boolean;
  readonly currentTask: TriSurfaceTaskState | null;
  readonly connectionEpoch: number;
  readonly lastSequenceNo: number;
  readonly bootstrapData: BootstrapSessionPayload | null;
  readonly changesList: readonly FileChangeItem[];

  openPanel: (panelId: DockablePanelId, position?: DockPosition) => void;
  closePanel: () => void;
  setDockPosition: (position: DockPosition) => void;
  toggleCollapse: () => void;
  updateTaskEvent: (
    event: Omit<TriSurfaceTaskState, 'epoch' | 'sequenceNo'> & {
      epoch?: number;
      sequenceNo?: number;
    }
  ) => boolean;
  resetEpochBaseline: (newEpoch: number) => void;
  applyBootstrapPayload: (payload: BootstrapSessionPayload) => void;
  resetStore: () => void;
}

export const useDockableWorkbenchStore = create<DockableWorkbenchState>((set, get) => {
  return {
    activePanelId: 'changes',
    dockPosition: 'right',
    isCollapsed: false,
    currentTask: {
      taskId: 'task-refactor-101',
      status: 'running',
      currentTool: 'write_file',
      stepIndex: 3,
      totalSteps: 5,
      epoch: 1,
      sequenceNo: 12,
      progressPercentage: 60,
      lastMessage: '已完成数据链路改造，正在生成自动化单元测试',
    },
    connectionEpoch: 1,
    lastSequenceNo: 12,
    bootstrapData: DEFAULT_BOOTSTRAP_PAYLOAD,
    changesList: DEFAULT_MOCK_CHANGES,

    openPanel: (panelId, position) => {
      set((state) => {
        return {
          activePanelId: panelId,
          dockPosition: position ?? (state.dockPosition === 'closed' ? 'right' : state.dockPosition),
          isCollapsed: false,
        };
      });
    },

    closePanel: () => {
      set({
        activePanelId: null,
        dockPosition: 'closed',
      });
    },

    setDockPosition: (position) => {
      set({ dockPosition: position });
    },

    toggleCollapse: () => {
      set((state) => {
        return { isCollapsed: !state.isCollapsed };
      });
    },

    updateTaskEvent: (event) => {
      const { connectionEpoch, lastSequenceNo } = get();
      const eventEpoch = event.epoch ?? connectionEpoch;
      const eventSeq = event.sequenceNo ?? lastSequenceNo + 1;

      const isValid = validateConnectionEpoch(
        eventEpoch,
        connectionEpoch,
        eventSeq,
        lastSequenceNo
      );

      if (!isValid) {
        return false;
      }

      set({
        currentTask: {
          taskId: event.taskId,
          status: event.status,
          currentTool: event.currentTool,
          stepIndex: event.stepIndex,
          totalSteps: event.totalSteps,
          epoch: eventEpoch,
          sequenceNo: eventSeq,
          progressPercentage: event.progressPercentage,
          lastMessage: event.lastMessage,
        },
        connectionEpoch: eventEpoch,
        lastSequenceNo: eventSeq,
      });

      return true;
    },

    resetEpochBaseline: (newEpoch) => {
      set({
        connectionEpoch: newEpoch,
        lastSequenceNo: 0,
      });
    },

    applyBootstrapPayload: (payload) => {
      set({
        bootstrapData: payload,
        changesList: payload.sandboxChanges,
        connectionEpoch: payload.eventBaselineEpoch,
        lastSequenceNo: 0,
      });
    },

    resetStore: () => {
      set({
        activePanelId: 'changes',
        dockPosition: 'right',
        isCollapsed: false,
        currentTask: null,
        connectionEpoch: 1,
        lastSequenceNo: 0,
        bootstrapData: null,
        changesList: DEFAULT_MOCK_CHANGES,
      });
    },
  };
});
