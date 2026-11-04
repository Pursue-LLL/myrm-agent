import { create } from 'zustand';
import type {
  CoordinationTelemetry,
  DAGNode,
  TeamConflictItem,
  TeamRuntimeState,
} from './teamRuntimeTypes';

const INITIAL_NODES: DAGNode[] = [
  {
    id: 'node_leader',
    label: '需求剖析与总控',
    type: 'leader',
    assigneeAgentName: '总控协调队长',
    status: 'completed',
    dependencies: [],
    deliverable: {
      deliverableId: 'deliv_req_01',
      version: 1,
      summary: '明确客户核心诉求为高可靠政企智能调度平台，交付周期 30 天。',
      decidedFacts: ['客户核心系统需满足 99.99% 可用性', '首期部署预算上限暂定 $35,000'],
      pendingRisksAndExceptions: ['暂未锁定私有化机房实际带宽', '多活数据同步延迟指标待测'],
      updatedAt: '10 分钟前',
    },
  },
  {
    id: 'node_architect',
    label: '高可用技术方案',
    type: 'architect',
    assigneeAgentName: '系统架构师',
    status: 'completed',
    dependencies: ['node_leader'],
    deliverable: {
      deliverableId: 'deliv_arch_01',
      version: 1,
      summary: '采用同城双活双中心部署方案，数据库跨可用区强一致同步。',
      decidedFacts: ['主备切换 RTO < 30 秒，RPO = 0', '服务器基线规格为 4 台 64C 高配节点'],
      pendingRisksAndExceptions: ['双活架构软硬件综合成本经测算达 $52,000/年，超出首期预算'],
      updatedAt: '6 分钟前',
    },
  },
  {
    id: 'node_finance',
    label: '财务报价与预算核算',
    type: 'evaluator',
    assigneeAgentName: '成本精算师',
    status: 'completed',
    dependencies: ['node_leader'],
    deliverable: {
      deliverableId: 'deliv_fin_01',
      version: 1,
      summary: '严格按照客户给定的 $35,000 预算上限制定成本支出明细表。',
      decidedFacts: ['硬件及云资源封顶 $28,000', '预留技术支持维保金 $7,000'],
      pendingRisksAndExceptions: ['若采用架构师的双活方案，成本缺口达 $17,000，合同面临亏损'],
      updatedAt: '4 分钟前',
    },
  },
  {
    id: 'node_compliance',
    label: '合规与数据出境审查',
    type: 'evaluator',
    assigneeAgentName: '法务合规顾问',
    status: 'completed',
    dependencies: ['node_architect'],
    deliverable: {
      deliverableId: 'deliv_law_01',
      version: 1,
      summary: '所有通信数据采用国密 SM4 加密，严格杜绝向公共境外云同步。',
      decidedFacts: ['本地化闭环日志存留 180 天', '签署数据主权不泄露保密契约'],
      pendingRisksAndExceptions: ['依赖架构师最终确定的节点跨区网络打通专线协议'],
      updatedAt: '2 分钟前',
    },
  },
  {
    id: 'node_finalizer',
    label: '投标文件与合同终稿',
    type: 'finalizer',
    assigneeAgentName: '终态交付员',
    status: 'running',
    dependencies: ['node_architect', 'node_finance', 'node_compliance'],
  },
];

const INITIAL_CONFLICTS: TeamConflictItem[] = [
  {
    id: 'conflict_arch_vs_budget',
    title: '高可用双活方案 vs 财务预算硬顶冲突',
    sourceNodeIds: ['node_architect', 'node_finance'],
    conflictDescription: '架构师规划的双活冗余架构年化成本需 $52,000，而财务根据客户要求严守 $35,000 上限，双方前提无法调和。',
    status: 'pending_arbitration',
    options: [
      {
        id: 'opt_sla_first',
        title: '可用性不可妥协（追加预算至 $52,000）',
        impactAnalysis: '保持 99.99% 双活容灾能力，向客户提报高可用增量溢价说明。',
        actionDirective: '指导财务更新预算基准为 $52,000，维持现有双活架构产出。',
      },
      {
        id: 'opt_budget_hard_cap',
        title: '预算红线不可突破（降级为单中心冷备）',
        impactAnalysis: '成本严格控制在 $35,000 以内，但主备切换 RTO 放宽至 30 分钟。',
        actionDirective: '通知架构师将同城双活降级为单中心高可用+冷备方案，重新生成技术文档。',
      },
    ],
  },
];

const INITIAL_TELEMETRY: CoordinationTelemetry = {
  preventedAlignmentsCount: 4,
  savedManualMinutes: 45,
  blockedBlindRerunsCount: 2,
  coordinationHealthScore: 94,
};

export const useTeamRuntimeStore = create<TeamRuntimeState>((set, get) => ({
  teamName: '政企智能调度数字专家团',
  nodes: INITIAL_NODES,
  conflicts: INITIAL_CONFLICTS,
  selectedNodeId: 'node_architect',
  activeConflictId: null,
  isDrawerOpen: false,
  telemetry: INITIAL_TELEMETRY,

  selectNode: (nodeId: string | null) => {
    set({
      selectedNodeId: nodeId,
      isDrawerOpen: nodeId !== null,
    });
  },

  openConflictModal: (conflictId: string) => {
    set({ activeConflictId: conflictId });
  },

  closeConflictModal: () => {
    set({ activeConflictId: null });
  },

  closeDrawer: () => {
    set({ isDrawerOpen: false, selectedNodeId: null });
  },

  updateNodeDeliverable: (nodeId: string, updatedSummary: string, newFacts: string[]) => {
    const { nodes, telemetry } = get();
    const targetNode = nodes.find((n) => n.id === nodeId);
    if (!targetNode || !targetNode.deliverable) {
      return;
    }

    const nextVersion = targetNode.deliverable.version + 1;
    const updatedDeliverable = {
      ...targetNode.deliverable,
      version: nextVersion,
      summary: updatedSummary,
      decidedFacts: newFacts,
      updatedAt: '刚刚',
    };

    // 递归标记所有直接与间接下游节点为前提失效 (stale_prerequisite)
    const downstreamIds = new Set<string>();
    const findDownstream = (currentId: string) => {
      for (const node of nodes) {
        if (node.dependencies.includes(currentId)) {
          downstreamIds.add(node.id);
          findDownstream(node.id);
        }
      }
    };
    findDownstream(nodeId);

    const updatedNodes = nodes.map((n) => {
      if (n.id === nodeId) {
        return { ...n, deliverable: updatedDeliverable };
      }
      if (downstreamIds.has(n.id)) {
        return {
          ...n,
          status: 'stale_prerequisite' as const,
          staleReason: `上游节点「${targetNode.label}」交付物已更新至 v${nextVersion}，当前输出基于旧前提，需对齐重评`,
        };
      }
      return n;
    });

    set({
      nodes: updatedNodes,
      telemetry: {
        ...telemetry,
        blockedBlindRerunsCount: telemetry.blockedBlindRerunsCount + downstreamIds.size,
        savedManualMinutes: telemetry.savedManualMinutes + 15,
      },
    });
  },

  arbitrateConflict: (conflictId: string, optionId: string) => {
    const { conflicts, telemetry } = get();
    const updatedConflicts = conflicts.map((c) => {
      if (c.id === conflictId) {
        return {
          ...c,
          status: 'resolved' as const,
          selectedOptionId: optionId,
          arbitratedAt: new Date().toISOString(),
        };
      }
      return c;
    });

    set({
      conflicts: updatedConflicts,
      telemetry: {
        ...telemetry,
        preventedAlignmentsCount: telemetry.preventedAlignmentsCount + 1,
        savedManualMinutes: telemetry.savedManualMinutes + 20,
        coordinationHealthScore: Math.min(100, telemetry.coordinationHealthScore + 3),
      },
    });
  },

  resetTeamRuntimeState: () => {
    set({
      teamName: '政企智能调度数字专家团',
      nodes: INITIAL_NODES,
      conflicts: INITIAL_CONFLICTS,
      selectedNodeId: 'node_architect',
      activeConflictId: null,
      isDrawerOpen: false,
      telemetry: INITIAL_TELEMETRY,
    });
  },
}));
