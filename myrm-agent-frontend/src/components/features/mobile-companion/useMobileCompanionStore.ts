import { create } from 'zustand';
import {
  MobileCompanionState,
  MobileCompanionTask,
  PairingSessionConfig,
} from './mobileCompanionTypes';
import { generatePairingConfig } from './mobileCompanionEngine';

export interface MobileCompanionActions {
  openPairingModal: (sessionId: string) => void;
  closePairingModal: () => void;
  connectToSession: (sessionId: string, token: string) => void;
  updateTaskSnapshot: (update: Partial<MobileCompanionTask>) => void;
  approvePendingAction: (approved: boolean, feedback?: string) => void;
  sendRemoteSteering: (instruction: string) => void;
  toggleRemoteSteering: (open?: boolean) => void;
  reset: () => void;
}

export type MobileCompanionStore = MobileCompanionState & MobileCompanionActions;

const INITIAL_MOCK_TASK: MobileCompanionTask = {
  sessionId: 'sess-long-run-mobile-8848',
  taskName: '书画作品定制报价工具自动化交付',
  phase: 'testing',
  progress: 68,
  estimatedSecondsRemaining: 145,
  startedAt: Date.now() - 360 * 1000,
  latestScreenshot: {
    id: 'shot-1',
    timestamp: Date.now() - 30 * 1000,
    url: 'https://images.unsplash.com/photo-1551288049-bebda4e38f71?auto=format&fit=crop&w=600&q=80',
    title: '沙箱内定制界面已完成表单渲染并进入计算测试',
  },
  pendingApproval: {
    id: 'appr-1',
    toolName: 'execute_shell_command',
    description: '尝试在沙箱容器中执行：npm install xlsx --save 以增加 Excel 导出支持',
    riskLevel: 'medium',
    params: {
      command: 'npm install xlsx',
      cwd: '/workspace/custom-quoter',
    },
  },
  artifacts: [
    {
      id: 'art-1',
      name: 'quoter_spec_v1.json',
      type: 'document',
      size: 1024 * 12,
      downloadUrl: '/artifacts/quoter_spec_v1.json',
    },
    {
      id: 'art-2',
      name: 'QuoterCalculator.tsx',
      type: 'code',
      size: 1024 * 34,
      downloadUrl: '/artifacts/QuoterCalculator.tsx',
    },
  ],
  highSnrSummary: [
    '已完成需求前置澄清，锁定克制 V1 规范与 Non-goals',
    '已搭建单页响应式布局，完成尺寸与材质动态系数公式',
    '正在沙箱中运行 12 组边缘测试用例（覆盖超大尺寸与非标材料）',
  ],
};

const INITIAL_STATE: MobileCompanionState = {
  isPairingModalOpen: false,
  pairingConfig: null,
  activeTask: INITIAL_MOCK_TASK,
  isRemoteSteeringOpen: false,
  sentSteeringCommands: [],
  isConnected: true,
};

export const useMobileCompanionStore = create<MobileCompanionStore>((set, get) => ({
  ...INITIAL_STATE,

  openPairingModal: (sessionId: string) => {
    const config: PairingSessionConfig = generatePairingConfig(sessionId);
    set({
      isPairingModalOpen: true,
      pairingConfig: config,
    });
  },

  closePairingModal: () => {
    set({ isPairingModalOpen: false });
  },

  connectToSession: (sessionId: string, _token: string) => {
    set({
      isConnected: true,
      activeTask: {
        ...INITIAL_MOCK_TASK,
        sessionId,
      },
    });
  },

  updateTaskSnapshot: (update: Partial<MobileCompanionTask>) => {
    const current = get().activeTask;
    if (!current) {
      return;
    }

    set({
      activeTask: {
        ...current,
        ...update,
      },
    });
  },

  approvePendingAction: (approved: boolean, feedback?: string) => {
    const current = get().activeTask;
    if (!current || !current.pendingApproval) {
      return;
    }

    const newLogs = [...current.highSnrSummary];
    if (approved) {
      newLogs.push(`[手机端批准] 已授权执行高危工具: ${current.pendingApproval.toolName}`);
    } else {
      newLogs.push(
        `[手机端拒绝] 已拦截工具执行: ${current.pendingApproval.toolName}${
          feedback ? ` (原因: ${feedback})` : ''
        }`
      );
    }

    set({
      activeTask: {
        ...current,
        phase: approved ? 'testing' : 'paused_approval',
        pendingApproval: undefined,
        highSnrSummary: newLogs,
      },
    });
  },

  sendRemoteSteering: (instruction: string) => {
    const trimmed = instruction.trim();
    if (!trimmed) {
      return;
    }

    const { activeTask, sentSteeringCommands } = get();
    const updatedCommands = [...sentSteeringCommands, trimmed];

    if (activeTask) {
      const updatedLogs = [
        ...activeTask.highSnrSummary,
        `[随行微调已回传] 手机端远程补充指令: “${trimmed}”`,
      ];
      set({
        activeTask: {
          ...activeTask,
          highSnrSummary: updatedLogs,
        },
        sentSteeringCommands: updatedCommands,
        isRemoteSteeringOpen: false,
      });
      return;
    }

    set({
      sentSteeringCommands: updatedCommands,
      isRemoteSteeringOpen: false,
    });
  },

  toggleRemoteSteering: (open?: boolean) => {
    set((state) => ({
      isRemoteSteeringOpen:
        open !== undefined ? open : !state.isRemoteSteeringOpen,
    }));
  },

  reset: () => {
    set(INITIAL_STATE);
  },
}));
