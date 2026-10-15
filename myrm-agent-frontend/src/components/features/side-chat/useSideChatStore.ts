import { create } from 'zustand';
import {
  MainTaskProgressInfo,
  SideChatMessage,
  SideChatState,
  SteeringBufferItem,
} from './sideChatTypes';
import {
  classifySideChatIntent,
  createSteeringItemFromMessage,
  generateInstantCollaboratorReply,
} from './sideChatEngine';

export interface SideChatActions {
  setOpen: (open: boolean) => void;
  setDocked: (docked: boolean) => void;
  sendSideMessage: (content: string) => void;
  consumeSteeringInNextStep: (stepNumber: number) => SteeringBufferItem[];
  updateMainTaskProgress: (progress: Partial<MainTaskProgressInfo>) => void;
  dismissSteeringItem: (itemId: string) => void;
  clearMessages: () => void;
  reset: () => void;
}

export type SideChatStore = SideChatState & SideChatActions;

const INITIAL_MAIN_TASK: MainTaskProgressInfo = {
  taskId: 'task-long-run-1',
  taskName: '书画定制报价工具自动化交付',
  status: 'running',
  currentStep: 2,
  totalSteps: 5,
  currentStepDescription: '正在沙箱中编译计算公式核心模块并运行单元测试...',
};

const INITIAL_STATE: SideChatState = {
  isOpen: false,
  isDocked: false,
  messages: [],
  steeringQueue: [],
  mainTask: INITIAL_MAIN_TASK,
  unreadCount: 0,
};

export const useSideChatStore = create<SideChatStore>((set, get) => ({
  ...INITIAL_STATE,

  setOpen: (open: boolean) => {
    set({
      isOpen: open,
      unreadCount: open ? 0 : get().unreadCount,
    });
  },

  setDocked: (docked: boolean) => {
    set({ isDocked: docked });
  },

  sendSideMessage: (content: string) => {
    const trimmed = content.trim();
    if (!trimmed) {
      return;
    }

    const { mainTask, isOpen, messages, steeringQueue } = get();
    const intent = classifySideChatIntent(trimmed);
    const userMsgId = `side-user-${Date.now()}-${Math.random().toString(36).substring(2, 6)}`;

    const isDirectInquiry = intent === 'status_inquiry';
    const steeringStatus = isDirectInquiry ? 'instant_answered' : 'pending_injection';

    const userMessage: SideChatMessage = {
      id: userMsgId,
      role: 'user',
      content: trimmed,
      timestamp: Date.now(),
      intentType: intent,
      steeringStatus,
    };

    let newQueue = steeringQueue;
    if (!isDirectInquiry) {
      const queueItem = createSteeringItemFromMessage(userMessage);
      newQueue = [...steeringQueue, queueItem];
    }

    // 协作者 Agent 毫秒级生成回复
    const assistantReplyText = generateInstantCollaboratorReply(intent, trimmed, mainTask);
    const assistantMsg: SideChatMessage = {
      id: `side-asst-${Date.now()}-${Math.random().toString(36).substring(2, 6)}`,
      role: 'assistant',
      content: assistantReplyText,
      timestamp: Date.now() + 10,
    };

    set({
      messages: [...messages, userMessage, assistantMsg],
      steeringQueue: newQueue,
      unreadCount: isOpen ? 0 : get().unreadCount + 1,
    });
  },

  consumeSteeringInNextStep: (stepNumber: number) => {
    const { steeringQueue, messages } = get();
    const pendingItems = steeringQueue.filter((i) => i.status === 'pending');

    if (pendingItems.length === 0) {
      return [];
    }

    const consumedSourceIds = new Set(pendingItems.map((i) => i.sourceMessageId));

    // 更新队列状态
    const updatedQueue = steeringQueue.map((item) => {
      if (item.status === 'pending') {
        return {
          ...item,
          status: 'consumed' as const,
          consumedAtStep: stepNumber,
        };
      }
      return item;
    });

    // 更新原消息中的注入状态
    const updatedMessages = messages.map((msg) => {
      if (consumedSourceIds.has(msg.id)) {
        return {
          ...msg,
          steeringStatus: 'injected_to_main' as const,
          injectedAtStep: stepNumber,
        };
      }
      return msg;
    });

    // 插入一条系统广播告知主 Agent 已成功平滑吸收
    const sysMsg: SideChatMessage = {
      id: `side-sys-${Date.now()}`,
      role: 'system',
      content: `[主沙箱步进同步] 主任务在第 ${stepNumber} 步已成功吸收并合入 ${pendingItems.length} 条支线微调指令。`,
      timestamp: Date.now(),
    };

    set({
      steeringQueue: updatedQueue,
      messages: [...updatedMessages, sysMsg],
    });

    return pendingItems;
  },

  updateMainTaskProgress: (progress: Partial<MainTaskProgressInfo>) => {
    set((state) => ({
      mainTask: {
        ...state.mainTask,
        ...progress,
      },
    }));
  },

  dismissSteeringItem: (itemId: string) => {
    set((state) => {
      const updatedQueue = state.steeringQueue.map((item) => {
        if (item.id === itemId) {
          return {
            ...item,
            status: 'cancelled' as const,
          };
        }
        return item;
      });

      const targetItem = state.steeringQueue.find((i) => i.id === itemId);
      const updatedMessages = state.messages.map((msg) => {
        if (targetItem && msg.id === targetItem.sourceMessageId) {
          return {
            ...msg,
            steeringStatus: 'discarded' as const,
          };
        }
        return msg;
      });

      return {
        steeringQueue: updatedQueue,
        messages: updatedMessages,
      };
    });
  },

  clearMessages: () => {
    set({
      messages: [],
      steeringQueue: [],
      unreadCount: 0,
    });
  },

  reset: () => {
    set(INITIAL_STATE);
  },
}));
