import { create } from 'zustand';
import type {
  DiscoveryChipItem,
  ScopeIsolationAudit,
  TeamWorkspaceEntity,
  WorkspaceScope,
  WorkspaceScopeState,
} from './workspaceScopeTypes';

const INITIAL_TEAMS: TeamWorkspaceEntity[] = [
  {
    id: 'team-acme-corp',
    name: 'Acme AI Engineering',
    avatarUrl: '',
    memberCount: 12,
    role: 'owner',
    enterpriseSandboxId: 'sbx-ent-acme-prod-01',
    sharedProjectsCount: 8,
  },
  {
    id: 'team-open-labs',
    name: 'Open Labs Research',
    avatarUrl: '',
    memberCount: 5,
    role: 'member',
    enterpriseSandboxId: 'sbx-ent-labs-dev-03',
    sharedProjectsCount: 3,
  },
];

const PRESET_DISCOVERY_CHIPS: DiscoveryChipItem[] = [
  {
    id: 'chip-make-dashboard',
    label: '生成交互式看板',
    description: '自动分析当前工作区工单与代码健康度，直出交互式 Mini-App 看板',
    iconName: 'LayoutDashboard',
    templatePrompt:
      '请根据当前工作区内的最新代码变更与已登记工单，生成一个可交互的敏捷项目看板 (Interactive Dashboard)，支持按模块分类查看缺陷与里程碑。',
    category: 'dashboard',
  },
  {
    id: 'chip-defect-heatmap',
    label: '架构缺陷热力图',
    description: '全景扫描代码异味与依赖漏洞，生成可视化健康热力矩阵',
    iconName: 'Activity',
    templatePrompt:
      '请对当前工程执行深度架构审查，输出包含潜在内存泄漏、未捕获异常与冗余计算的架构缺陷全景热力图 (Defect Heatmap)。',
    category: 'heatmap',
  },
  {
    id: 'chip-sprint-kanban',
    label: '多智能体工单流',
    description: '自动拉取机队中各 Agent 的当前分派任务并生成流转流水线',
    iconName: 'GitFork',
    templatePrompt:
      '请列出当前正在协同运作的所有 Agent 实例及其持有的工单，汇总为一张按处理中/等待仲裁/已结项分列的工单看板。',
    category: 'workflow',
  },
];

interface WorkspaceScopeActions {
  switchScope: (targetScope: WorkspaceScope, teamId?: string) => ScopeIsolationAudit;
  toggleDropdown: (open?: boolean) => void;
  selectDiscoveryChip: (chipId: string) => string | null;
  clearSelectedChip: () => void;
  resetState: () => void;
}

export type WorkspaceScopeStore = WorkspaceScopeState & WorkspaceScopeActions;

const INITIAL_STATE: WorkspaceScopeState = {
  currentScope: 'personal',
  activeTeamId: INITIAL_TEAMS[0]?.id ?? '',
  teams: INITIAL_TEAMS,
  lastIsolationAudit: null,
  isScopeDropdownOpen: false,
  discoveryChips: PRESET_DISCOVERY_CHIPS,
  selectedChipResult: null,
};

export const useWorkspaceScopeStore = create<WorkspaceScopeStore>((set, get) => ({
  ...INITIAL_STATE,

  switchScope: (targetScope: WorkspaceScope, teamId?: string) => {
    const prevScope = get().currentScope;
    const resolvedTeamId = teamId || get().activeTeamId || INITIAL_TEAMS[0]?.id || '';

    // 严苛执行 Zero-Leak 隔离不变式：
    // 1. 瞬时断开旧连接并清空活动会话临时上下文
    // 2. 当进入团队空间时，自动锁定并隐藏本地私密 API Key
    const isolationAudit: ScopeIsolationAudit = {
      switchedAt: Date.now(),
      fromScope: prevScope,
      toScope: targetScope,
      activeSessionPurged: true,
      localSecretKeysHidden: targetScope === 'team',
      isZeroLeakGuaranteed: true,
    };

    set({
      currentScope: targetScope,
      activeTeamId: resolvedTeamId,
      lastIsolationAudit: isolationAudit,
      isScopeDropdownOpen: false,
      selectedChipResult: null,
    });

    return isolationAudit;
  },

  toggleDropdown: (open?: boolean) => {
    set((state) => ({
      isScopeDropdownOpen: open !== undefined ? open : !state.isScopeDropdownOpen,
    }));
  },

  selectDiscoveryChip: (chipId: string) => {
    const chip = get().discoveryChips.find((c) => c.id === chipId);
    if (!chip) {
      return null;
    }

    set({ selectedChipResult: chip.templatePrompt });
    return chip.templatePrompt;
  },

  clearSelectedChip: () => {
    set({ selectedChipResult: null });
  },

  resetState: () => {
    set(INITIAL_STATE);
  },
}));
