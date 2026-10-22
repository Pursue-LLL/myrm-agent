import { create } from 'zustand';
import {
  LongTaskDispatchTicket,
  PushNotificationChannel,
  TaskSourcedChecklistItem,
} from './longTaskNotifyTypes';
import { simulatePushNotificationPayload } from './longTaskRejoinEngine';

export interface LongTaskNotifyState {
  activeTask: LongTaskDispatchTicket | null;
  taskHistory: LongTaskDispatchTicket[];
  isDispatchModalOpen: boolean;
  isReviewModalOpen: boolean;
  isNotificationGranted: boolean;
  isBackgrounded: boolean;
  lastSyncTimestamp: number;

  // Actions
  openDispatchModal: () => void;
  closeDispatchModal: () => void;
  openReviewModal: () => void;
  closeReviewModal: () => void;
  requestNotificationPermission: () => Promise<boolean>;
  dispatchTask: (params: {
    title: string;
    prompt: string;
    estimatedDurationSec?: number;
    notifyWebPush: boolean;
    notifySystem: boolean;
  }) => LongTaskDispatchTicket;
  simulateStepProgress: (stepName: string, progressPercent: number) => void;
  toggleBackgroundMode: (isBackground: boolean) => void;
  rejoinActiveTask: () => void;
  completeTask: () => void;
  resetState: () => void;
}

const DEFAULT_CHECKLIST: TaskSourcedChecklistItem[] = [
  {
    id: 'chk-1',
    title: '全量竞品定价与阶梯策略对比矩阵',
    sourceUrl: 'https://benchmark.enterprise.ai/pricing/q3-matrix',
    sourceTitle: '企业软件采购与定价分析白皮书 (2026)',
    verified: true,
    snippet: '抓取5家竞品商业计划书并交叉校验月付/年付折扣结构。',
    timestamp: Date.now() - 60000,
  },
  {
    id: 'chk-2',
    title: '云端沙箱合规与SOC2审计条款',
    sourceUrl: 'https://security.trust-cloud.io/compliance/soc2-type-ii',
    sourceTitle: '独立沙箱合规标准认证公示',
    verified: true,
    snippet: '已确认隔离沙箱容器符合金融级数据留存规范。',
    timestamp: Date.now() - 30000,
  },
];

const INITIAL_TASK: LongTaskDispatchTicket = {
  taskId: 'task-long-9821',
  title: '全网竞品商业模式深度调研与沙箱压测报告',
  prompt: '抓取5家主流竞品定价与SLA条款，跑通压测并提炼带来源结论清单',
  estimatedDurationSec: 180, // 3 分钟长任务
  executionEnv: 'cloud-server',
  notifyChannels: ['web-push', 'system-toast'],
  startedAt: Date.now() - 90000,
  status: 'running_unattended',
  progressPercent: 65,
  currentStep: '第3步：正在生成各家厂商SLA与技术差异雷达图',
  sourcedChecklist: DEFAULT_CHECKLIST,
  pushSent: false,
};

export const useLongTaskNotifyStore = create<LongTaskNotifyState>((set, get) => ({
  activeTask: INITIAL_TASK,
  taskHistory: [],
  isDispatchModalOpen: false,
  isReviewModalOpen: false,
  isNotificationGranted: true,
  isBackgrounded: false,
  lastSyncTimestamp: Date.now(),

  openDispatchModal: () => {
    set({ isDispatchModalOpen: true });
  },

  closeDispatchModal: () => {
    set({ isDispatchModalOpen: false });
  },

  openReviewModal: () => {
    set({ isReviewModalOpen: true });
  },

  closeReviewModal: () => {
    set({ isReviewModalOpen: false });
  },

  requestNotificationPermission: async () => {
    if (typeof window !== 'undefined' && 'Notification' in window) {
      const permission = await Notification.requestPermission();
      const granted = permission === 'granted';
      set({ isNotificationGranted: granted });
      return granted;
    }
    set({ isNotificationGranted: true });
    return true;
  },

  dispatchTask: ({
    title,
    prompt,
    estimatedDurationSec = 180,
    notifyWebPush,
    notifySystem,
  }) => {
    const notifyChannels: PushNotificationChannel[] = [];
    if (notifyWebPush) {
      notifyChannels.push('web-push');
    }
    if (notifySystem) {
      notifyChannels.push('system-toast');
    }

    const newTask: LongTaskDispatchTicket = {
      taskId: `task-long-${Date.now()}`,
      title,
      prompt,
      estimatedDurationSec,
      executionEnv: 'cloud-server',
      notifyChannels,
      startedAt: Date.now(),
      status: 'running_unattended',
      progressPercent: 5,
      currentStep: '初始化常驻云端执行上下文，瘦客户端切后台不受影响',
      sourcedChecklist: [],
      pushSent: false,
    };

    set({
      activeTask: newTask,
      isDispatchModalOpen: false,
      lastSyncTimestamp: Date.now(),
    });

    if (typeof window !== 'undefined') {
      window.dispatchEvent(
        new CustomEvent('myrm:long-task-dispatched', {
          detail: {
            taskId: newTask.taskId,
            title: newTask.title,
            notifyChannels: newTask.notifyChannels,
          },
        })
      );
    }

    return newTask;
  },

  simulateStepProgress: (stepName, progressPercent) => {
    const { activeTask } = get();
    if (!activeTask || activeTask.status !== 'running_unattended') {
      return;
    }

    set({
      activeTask: {
        ...activeTask,
        currentStep: stepName,
        progressPercent: Math.min(100, Math.max(0, progressPercent)),
      },
      lastSyncTimestamp: Date.now(),
    });
  },

  toggleBackgroundMode: (isBackground) => {
    set({
      isBackgrounded: isBackground,
      lastSyncTimestamp: Date.now(),
    });
  },

  rejoinActiveTask: () => {
    set({
      isBackgrounded: false,
      lastSyncTimestamp: Date.now(),
    });

    if (typeof window !== 'undefined') {
      window.dispatchEvent(
        new CustomEvent('myrm:long-task-rejoined', {
          detail: {
            taskId: get().activeTask?.taskId,
            syncTimestamp: Date.now(),
          },
        })
      );
    }
  },

  completeTask: () => {
    const { activeTask, taskHistory } = get();
    if (!activeTask) {
      return;
    }

    const completed: LongTaskDispatchTicket = {
      ...activeTask,
      status: 'completed',
      progressPercent: 100,
      completedAt: Date.now(),
      currentStep: '任务已顺利完成，带来源权威清单就绪',
      pushSent: true,
      sourcedChecklist:
        activeTask.sourcedChecklist.length > 0
          ? activeTask.sourcedChecklist
          : DEFAULT_CHECKLIST,
    };

    set({
      activeTask: completed,
      taskHistory: [completed, ...taskHistory],
      isReviewModalOpen: true,
      lastSyncTimestamp: Date.now(),
    });

    if (typeof window !== 'undefined') {
      const payload = simulatePushNotificationPayload(completed);
      window.dispatchEvent(
        new CustomEvent('myrm:long-task-completed', {
          detail: {
            taskId: completed.taskId,
            payload,
          },
        })
      );
    }
  },

  resetState: () => {
    set({
      activeTask: INITIAL_TASK,
      taskHistory: [],
      isDispatchModalOpen: false,
      isReviewModalOpen: false,
      isNotificationGranted: true,
      isBackgrounded: false,
      lastSyncTimestamp: Date.now(),
    });
  },
}));
