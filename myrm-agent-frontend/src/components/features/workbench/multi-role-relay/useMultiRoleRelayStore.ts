import { create } from 'zustand';
import {
  ArtifactForkBranch,
  RelayStage,
  StageArtifactSnapshot,
} from './multiRoleRelayTypes';
import {
  advanceRelayPipeline,
  createArtifactForkBranch,
} from './relayPipelineEngine';

export interface MultiRoleRelayState {
  stages: RelayStage[];
  activeStageId: string;
  selectedSnapshot: StageArtifactSnapshot | null;
  activeForkBranch: ArtifactForkBranch | null;
  isDiffStudioOpen: boolean;
  forkHistory: ArtifactForkBranch[];

  // Actions
  selectStageSnapshot: (stageId: string) => void;
  openDiffStudio: (snapshotId?: string) => void;
  closeDiffStudio: () => void;
  createFork: (
    branchName: string,
    modifiedContent: string,
    note?: string
  ) => ArtifactForkBranch | null;
  applyForkBranch: (branchId: string) => void;
  advancePipeline: (outputSnapshot?: StageArtifactSnapshot) => void;
  resetState: () => void;
}

const INITIAL_STAGES: RelayStage[] = [
  {
    id: 'stage-researcher',
    stepNumber: 1,
    role: 'researcher',
    roleName: '调研员',
    status: 'completed',
    actionSummary: '全网检索抓取5家主流竞品商业定价模型与技术参数',
    durationMs: 4200,
    startedAt: Date.now() - 15000,
    completedAt: Date.now() - 10800,
    snapshot: {
      id: 'snap-researcher-1',
      stageId: 'stage-researcher',
      role: 'researcher',
      roleName: '调研员',
      artifactName: '竞品全景对比矩阵.json',
      contentType: 'json',
      rawContent: `{\n  "VendorA": { "price": "$29/mo", "sla": "99.9%", "sandbox": true },\n  "VendorB": { "price": "$49/mo", "sla": "99.95%", "sandbox": false }\n}`,
      summary: '已结构化萃取两家头部竞品商业与稳定性基准数据',
      timestamp: Date.now() - 10800,
      tokenCount: 1420,
      version: 1,
    },
  },
  {
    id: 'stage-analyst',
    stepNumber: 2,
    role: 'analyst',
    roleName: '分析师',
    status: 'in_progress',
    actionSummary: '正在多维度测算商业护城河并提炼核心定价推荐',
    durationMs: 2800,
    startedAt: Date.now() - 10800,
    snapshot: {
      id: 'snap-analyst-1',
      stageId: 'stage-analyst',
      role: 'analyst',
      roleName: '分析师',
      artifactName: '商业护城河与定价建议.md',
      contentType: 'markdown',
      rawContent: `# 商业竞争策略推演\n1. 厂商A依托极低价格渗透中小客户，但SLA保障偏弱\n2. 建议我们采取 $39/mo 中位定价，绑定沙箱双向接管构建防御壁垒`,
      summary: '初步推导中位阶梯定价策略，拟绑定沙箱能力',
      timestamp: Date.now() - 5000,
      tokenCount: 960,
      version: 1,
    },
  },
  {
    id: 'stage-copywriter',
    stepNumber: 3,
    role: 'copywriter',
    roleName: '撰稿人',
    status: 'pending',
    actionSummary: '等待分析师交接中间产物，将成文化最终策划汇报案',
    durationMs: 0,
  },
];

export const useMultiRoleRelayStore = create<MultiRoleRelayState>((set, get) => ({
  stages: INITIAL_STAGES,
  activeStageId: 'stage-analyst',
  selectedSnapshot: INITIAL_STAGES[0].snapshot || null,
  activeForkBranch: null,
  isDiffStudioOpen: false,
  forkHistory: [],

  selectStageSnapshot: (stageId) => {
    const stage = get().stages.find((s) => s.id === stageId);
    if (stage && stage.snapshot) {
      set({
        selectedSnapshot: stage.snapshot,
        activeStageId: stage.id,
      });
    }
  },

  openDiffStudio: (snapshotId) => {
    const { stages, selectedSnapshot } = get();
    let target = selectedSnapshot;
    if (snapshotId) {
      for (const s of stages) {
        if (s.snapshot && s.snapshot.id === snapshotId) {
          target = s.snapshot;
          break;
        }
      }
    }
    if (target) {
      set({
        selectedSnapshot: target,
        isDiffStudioOpen: true,
      });
    }
  },

  closeDiffStudio: () => {
    set({ isDiffStudioOpen: false });
  },

  createFork: (branchName, modifiedContent, note) => {
    const { selectedSnapshot } = get();
    if (!selectedSnapshot) {
      return null;
    }

    const forkBranch = createArtifactForkBranch(
      selectedSnapshot,
      branchName,
      modifiedContent,
      note
    );

    set({ activeForkBranch: forkBranch });
    return forkBranch;
  },

  applyForkBranch: (branchId) => {
    const { activeForkBranch, stages } = get();
    if (!activeForkBranch || activeForkBranch.id !== branchId) {
      return;
    }

    const updatedBranch: ArtifactForkBranch = {
      ...activeForkBranch,
      status: 'applied',
    };

    const updatedStages = stages.map((stage) => {
      if (stage.id === activeForkBranch.stageId && stage.snapshot) {
        const updatedSnapshot: StageArtifactSnapshot = {
          ...stage.snapshot,
          rawContent: activeForkBranch.modifiedContent,
          version: stage.snapshot.version + 1,
          summary: `[用户分支调整: ${activeForkBranch.branchName}] ${stage.snapshot.summary}`,
        };
        return {
          ...stage,
          snapshot: updatedSnapshot,
        };
      }
      return stage;
    });

    set((state) => ({
      stages: updatedStages,
      activeForkBranch: null,
      isDiffStudioOpen: false,
      forkHistory: [updatedBranch, ...state.forkHistory],
      selectedSnapshot:
        updatedStages.find((s) => s.id === activeForkBranch.stageId)?.snapshot ||
        state.selectedSnapshot,
    }));

    if (typeof window !== 'undefined') {
      window.dispatchEvent(
        new CustomEvent('myrm:relay-artifact-forked', {
          detail: {
            branchId,
            stageId: activeForkBranch.stageId,
            branchName: activeForkBranch.branchName,
            userNote: activeForkBranch.userNote,
          },
        })
      );
    }
  },

  advancePipeline: (outputSnapshot) => {
    const { stages, activeStageId } = get();
    const nextStages = advanceRelayPipeline(stages, activeStageId, outputSnapshot);

    const nextInProgress = nextStages.find((s) => s.status === 'in_progress');
    const nextActiveId = nextInProgress ? nextInProgress.id : activeStageId;

    set({
      stages: nextStages,
      activeStageId: nextActiveId,
      selectedSnapshot:
        nextStages.find((s) => s.id === nextActiveId)?.snapshot ||
        get().selectedSnapshot,
    });
  },

  resetState: () => {
    set({
      stages: INITIAL_STAGES,
      activeStageId: 'stage-analyst',
      selectedSnapshot: INITIAL_STAGES[0].snapshot || null,
      activeForkBranch: null,
      isDiffStudioOpen: false,
      forkHistory: [],
    });
  },
}));
