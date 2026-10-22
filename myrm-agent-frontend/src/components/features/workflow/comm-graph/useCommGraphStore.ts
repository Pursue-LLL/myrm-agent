import { create } from 'zustand';
import type {
  AgentCommEvent,
  CommGraphState,
} from './commGraphTypes';

export const useCommGraphStore = create<CommGraphState>((set, get) => ({
  events: [],
  selectedEventId: null,
  isLive: false,
  returnCursorId: null,
  isPipelineInitializing: true,

  selectEvent: (eventId: string) => {
    set({
      selectedEventId: eventId,
      isLive: false,
    });
  },

  toggleLive: () => {
    const { isLive, events, selectedEventId, returnCursorId } = get();

    if (events.length === 0) {
      // 队列为空时严格禁止激活 Live，杜绝给用户造成死锁假象
      set({ isLive: false, selectedEventId: null, returnCursorId: null });
      return;
    }

    if (!isLive) {
      // 1. 用户从历史审阅步骤切入 Live 实时最新视角
      // 将当前停留的历史游标暂存到 returnCursorId 中，实现双向记忆
      const latestEventId = events[events.length - 1].id;
      set({
        isLive: true,
        returnCursorId: selectedEventId,
        selectedEventId: latestEventId,
      });
    } else {
      // 2. 用户在 Live 状态下再次点击 Live（退出实时视角，原位回溯）
      // 恢复原先被暂存的历史游标 returnCursorId
      let targetId = selectedEventId;
      if (returnCursorId !== null && events.some((e) => e.id === returnCursorId)) {
        targetId = returnCursorId;
      }

      set({
        isLive: false,
        selectedEventId: targetId,
        returnCursorId: null,
      });
    }
  },

  addCommEvent: (event: Omit<AgentCommEvent, 'id' | 'timestamp'>): string => {
    const id = `comm_evt_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
    const newEvent: AgentCommEvent = {
      ...event,
      id,
      timestamp: new Date().toISOString(),
    };

    set((state) => {
      const nextEvents = [...state.events, newEvent];
      const shouldFollow = state.isLive;

      return {
        events: nextEvents,
        isPipelineInitializing: false,
        // 如果当前是 Live 状态，自动滚动吸附到最新事件
        selectedEventId: shouldFollow ? id : (state.selectedEventId ?? id),
      };
    });

    return id;
  },

  clearEvents: () => {
    set({
      events: [],
      selectedEventId: null,
      isLive: false,
      returnCursorId: null,
      isPipelineInitializing: true,
    });
  },

  setPipelineInitializing: (initializing: boolean) => {
    set({ isPipelineInitializing: initializing });
  },

  resetState: () => {
    set({
      events: [],
      selectedEventId: null,
      isLive: false,
      returnCursorId: null,
      isPipelineInitializing: true,
    });
  },
}));
