import { create } from 'zustand';
import {
  BackgroundWorkerTask,
  ReanchoredResultCard,
  SpawnWorkerParams,
  StepNodeStatus,
  WorkerArtifactPayload,
  WorkerStepNode,
} from './fullDuplexBridgeTypes';

interface FullDuplexBridgeState {
  activeWorkers: Record<string, BackgroundWorkerTask>;
  isTrayDrawerOpen: boolean;
  reanchoredResults: ReanchoredResultCard[];
  unreadResultCount: number;

  spawnWorker: (params: SpawnWorkerParams) => string;
  updateWorkerProgress: (
    id: string,
    progress: number,
    currentStepLabel?: string,
  ) => void;
  advanceStep: (
    id: string,
    stepId: string,
    status: StepNodeStatus,
    detail?: string,
  ) => void;
  completeWorker: (id: string, artifact: WorkerArtifactPayload) => void;
  failWorker: (id: string, errorMessage: string) => void;
  cancelWorker: (id: string) => void;
  removeWorker: (id: string) => void;
  toggleTrayDrawer: (open?: boolean) => void;
  markResultAdopted: (resultId: string) => void;
  dismissResult: (resultId: string) => void;
  reset: () => void;
}

const INITIAL_MOCK_WORKERS: Record<string, BackgroundWorkerTask> = {
  'worker-crawl-1': {
    id: 'worker-crawl-1',
    title: '全网深度竞品爬取与特征比对',
    category: '竞品深度调研',
    status: 'running',
    progress: 45,
    currentStepLabel: '正在清洗并解析 18 个竞品的技术架构白皮书...',
    elapsedSec: 84,
    estimatedTotalSec: 180,
    spawnedAt: Date.now() - 84000,
    steps: [
      {
        id: 's1',
        label: '目标站点拓扑抓取',
        status: 'completed',
        detail: '完成 32 个域名的 DNS 与 SSL 扫描',
      },
      {
        id: 's2',
        label: '内容结构化解析与特征对齐',
        status: 'running',
        detail: '正在提取核心功能规格',
      },
      {
        id: 's3',
        label: '生成多维对比矩阵与决策建议',
        status: 'pending',
      },
    ],
  },
};

const INITIAL_MOCK_RESULTS: ReanchoredResultCard[] = [
  {
    id: 'res-report-01',
    workerId: 'worker-crawl-0',
    title: '2026 前沿 Agent 交互范式演化全景报告',
    category: '技术调研',
    elapsedSec: 142,
    isAdopted: false,
    createdAt: Date.now() - 60000,
    artifact: {
      id: 'art-01',
      title: 'FullDuplex_Interaction_Benchmark_v1.pdf',
      type: 'report',
      summary:
        '已梳理 OpenAI GPT-Live、Hermes Desktop 与 OpenClaw 2.0 三大体系的全双工架构指标与延迟对比。',
      previewSnippet:
        '前台会话平均响应 < 320ms，后台 Worker 吞吐提升 3.8 倍...',
    },
  },
];

let workerSeq = 0;

export const useFullDuplexBridgeStore = create<FullDuplexBridgeState>((set, get) => ({
  activeWorkers: INITIAL_MOCK_WORKERS,
  isTrayDrawerOpen: false,
  reanchoredResults: INITIAL_MOCK_RESULTS,
  unreadResultCount: 1,

  spawnWorker: (params: SpawnWorkerParams): string => {
    workerSeq += 1;
    const id = params.id ?? `worker-${Date.now()}-${workerSeq}`;
    const labels = params.stepLabels ?? ['初始化环境', '核心运算', '打包成果'];
    const steps: WorkerStepNode[] = labels.map((label, idx) => ({
      id: `step-${idx + 1}`,
      label,
      status: idx === 0 ? 'running' : 'pending',
    }));

    const newTask: BackgroundWorkerTask = {
      id,
      title: params.title,
      category: params.category ?? '后台任务',
      status: 'running',
      progress: 5,
      currentStepLabel: steps[0]?.label ?? '准备开始',
      steps,
      elapsedSec: 0,
      estimatedTotalSec: params.estimatedTotalSec ?? 120,
      spawnedAt: Date.now(),
    };

    set((state) => ({
      activeWorkers: {
        ...state.activeWorkers,
        [id]: newTask,
      },
    }));

    return id;
  },

  updateWorkerProgress: (
    id: string,
    progress: number,
    currentStepLabel?: string,
  ): void => {
    set((state) => {
      const existing = state.activeWorkers[id];
      if (!existing) {
        return state;
      }

      const clamped = Math.max(0, Math.min(100, Math.round(progress)));
      return {
        activeWorkers: {
          ...state.activeWorkers,
          [id]: {
            ...existing,
            progress: clamped,
            currentStepLabel: currentStepLabel ?? existing.currentStepLabel,
            status: clamped >= 100 ? 'completed' : existing.status,
          },
        },
      };
    });
  },

  advanceStep: (
    id: string,
    stepId: string,
    status: StepNodeStatus,
    detail?: string,
  ): void => {
    set((state) => {
      const existing = state.activeWorkers[id];
      if (!existing) {
        return state;
      }

      const updatedSteps = existing.steps.map((s) => {
        if (s.id === stepId) {
          return { ...s, status, detail: detail ?? s.detail };
        }
        return s;
      });

      return {
        activeWorkers: {
          ...state.activeWorkers,
          [id]: {
            ...existing,
            steps: updatedSteps,
          },
        },
      };
    });
  },

  completeWorker: (id: string, artifact: WorkerArtifactPayload): void => {
    const current = get().activeWorkers[id];
    const elapsed = current ? current.elapsedSec : 60;
    const title = current ? current.title : artifact.title;
    const category = current ? current.category : '后台成果';

    const newResult: ReanchoredResultCard = {
      id: `reanchor-${id}-${Date.now()}`,
      workerId: id,
      title,
      category,
      elapsedSec: elapsed,
      artifact,
      isAdopted: false,
      createdAt: Date.now(),
    };

    set((state) => {
      const existing = state.activeWorkers[id];
      const updatedWorkers = { ...state.activeWorkers };
      if (existing) {
        updatedWorkers[id] = {
          ...existing,
          status: 'completed',
          progress: 100,
          completedAt: Date.now(),
          artifact,
        };
      }

      return {
        activeWorkers: updatedWorkers,
        reanchoredResults: [newResult, ...state.reanchoredResults],
        unreadResultCount: state.unreadResultCount + 1,
      };
    });
  },

  failWorker: (id: string, errorMessage: string): void => {
    set((state) => {
      const existing = state.activeWorkers[id];
      if (!existing) {
        return state;
      }

      return {
        activeWorkers: {
          ...state.activeWorkers,
          [id]: {
            ...existing,
            status: 'failed',
            errorMessage,
          },
        },
      };
    });
  },

  cancelWorker: (id: string): void => {
    set((state) => {
      const existing = state.activeWorkers[id];
      if (!existing) {
        return state;
      }

      return {
        activeWorkers: {
          ...state.activeWorkers,
          [id]: {
            ...existing,
            status: 'canceled',
          },
        },
      };
    });
  },

  removeWorker: (id: string): void => {
    set((state) => {
      const next = { ...state.activeWorkers };
      delete next[id];
      return { activeWorkers: next };
    });
  },

  toggleTrayDrawer: (open?: boolean): void => {
    set((state) => ({
      isTrayDrawerOpen: open !== undefined ? open : !state.isTrayDrawerOpen,
      unreadResultCount: 0,
    }));
  },

  markResultAdopted: (resultId: string): void => {
    set((state) => ({
      reanchoredResults: state.reanchoredResults.map((r) => {
        if (r.id === resultId) {
          return { ...r, isAdopted: true };
        }
        return r;
      }),
    }));
  },

  dismissResult: (resultId: string): void => {
    set((state) => ({
      reanchoredResults: state.reanchoredResults.filter((r) => r.id !== resultId),
    }));
  },

  reset: (): void => {
    set({
      activeWorkers: {},
      isTrayDrawerOpen: false,
      reanchoredResults: [],
      unreadResultCount: 0,
    });
  },
}));
