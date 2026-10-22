/**
 * useSwarmCanvasStore.ts
 * 多智能体弹性网格画布、动态并发聚焦透镜与集群状态管理
 */

import { create } from 'zustand';
import type {
  SwarmWorkerItem,
  SwarmWorkerStatus,
} from './swarmCanvasTypes';

export interface SwarmCanvasStoreState {
  workers: SwarmWorkerItem[];
  focusedWorkerId: string | null;
  isLensDrawerOpen: boolean;
  statusFilter: SwarmWorkerStatus | 'all';

  // Actions
  setWorkers: (workers: SwarmWorkerItem[]) => void;
  updateWorker: (workerId: string, partial: Partial<SwarmWorkerItem>) => void;
  focusWorker: (workerId: string) => void;
  closeLens: () => void;
  steerWorker: (workerId: string, instruction: string) => void;
  stopWorker: (workerId: string) => void;
  setStatusFilter: (filter: SwarmWorkerStatus | 'all') => void;
  resetAll: () => void;
}

const mockInitialWorkers: SwarmWorkerItem[] = [
  {
    id: 'worker-crawl-01',
    name: '全网情报抓取工',
    role: '外部信源分析师',
    colorTheme: '#3b82f6',
    status: 'completed',
    currentTaskTitle: '抓取 Qoder 与 Codex 最新公开实测技术评测',
    progressPercent: 100,
    thinkingLogs: ['解析 HTML 节点', '提取结构化文本摘要', '写入向量数据库'],
    toolCalls: [
      { id: 'c1', toolName: 'web_crawler', summary: '抓取微信公众号文章' },
    ],
    createdAt: Date.now() - 30000,
  },
  {
    id: 'worker-finance-02',
    name: '金融因果沙盘推演师',
    role: '产业链精算师',
    colorTheme: '#10b981',
    status: 'running',
    currentTaskTitle: '运行 Python 敏感度矩阵计算上下游波动',
    progressPercent: 65,
    thinkingLogs: ['调用 Numpy 计算利润率弹性', '生成敏感度箱线图'],
    toolCalls: [
      { id: 'c2', toolName: 'python_sandbox', summary: '执行 Monte Carlo 模拟' },
    ],
    createdAt: Date.now() - 20000,
  },
  {
    id: 'worker-auth-03',
    name: '安全授权审计官',
    role: '高危工具审批哨兵',
    colorTheme: '#f59e0b',
    status: 'waiting_approval',
    currentTaskTitle: '等待用户确认是否执行远程服务器配置覆盖',
    progressPercent: 40,
    thinkingLogs: ['拦截破坏性命令', '生成风险提示弹窗'],
    toolCalls: [
      { id: 'c3', toolName: 'ssh_exec', summary: '尝试写入生产环境配置' },
    ],
    createdAt: Date.now() - 10000,
  },
  {
    id: 'worker-ui-04',
    name: 'Canvas 富媒体渲染器',
    role: '自适应前端工程师',
    colorTheme: '#8b5cf6',
    status: 'running',
    currentTaskTitle: '编译内嵌 CSS Inliner 富文本排版工件',
    progressPercent: 80,
    thinkingLogs: ['编译薄荷清新主题', '导出单文件 HTML'],
    toolCalls: [
      { id: 'c4', toolName: 'css_inliner', summary: '生成样式内联文件' },
    ],
    createdAt: Date.now() - 15000,
  },
  {
    id: 'worker-sync-05',
    name: '数据跨端迁移同步引擎',
    role: '旧版数据平滑迁移专员',
    colorTheme: '#ec4899',
    status: 'idle',
    currentTaskTitle: '后台监听旧版配置与定时任务变更',
    progressPercent: 10,
    thinkingLogs: ['扫描本地 SQLite 路径', '就绪等待触发'],
    toolCalls: [],
    createdAt: Date.now() - 5000,
  },
];

export const useSwarmCanvasStore = create<SwarmCanvasStoreState>((set) => ({
  workers: mockInitialWorkers,
  focusedWorkerId: null,
  isLensDrawerOpen: false,
  statusFilter: 'all',

  setWorkers: (workers: SwarmWorkerItem[]): void => {
    set({ workers });
  },

  updateWorker: (workerId: string, partial: Partial<SwarmWorkerItem>): void => {
    set((state) => ({
      workers: state.workers.map((w) =>
        w.id === workerId ? { ...w, ...partial } : w
      ),
    }));
  },

  focusWorker: (workerId: string): void => {
    set({
      focusedWorkerId: workerId,
      isLensDrawerOpen: true,
    });
  },

  closeLens: (): void => {
    set({
      isLensDrawerOpen: false,
      focusedWorkerId: null,
    });
  },

  steerWorker: (workerId: string, instruction: string): void => {
    set((state) => ({
      workers: state.workers.map((w) => {
        if (w.id === workerId) {
          return {
            ...w,
            status: 'running',
            thinkingLogs: [
              ...w.thinkingLogs,
              `[人工纠偏] 收到用户指令: ${instruction}`,
            ],
          };
        }
        return w;
      }),
    }));
  },

  stopWorker: (workerId: string): void => {
    set((state) => ({
      workers: state.workers.map((w) => {
        if (w.id === workerId) {
          return {
            ...w,
            status: 'failed',
            thinkingLogs: [...w.thinkingLogs, '[用户干预] 已手动终止此子任务'],
          };
        }
        return w;
      }),
    }));
  },

  setStatusFilter: (filter: SwarmWorkerStatus | 'all'): void => {
    set({ statusFilter: filter });
  },

  resetAll: (): void => {
    set({
      workers: [],
      focusedWorkerId: null,
      isLensDrawerOpen: false,
      statusFilter: 'all',
    });
  },
}));
