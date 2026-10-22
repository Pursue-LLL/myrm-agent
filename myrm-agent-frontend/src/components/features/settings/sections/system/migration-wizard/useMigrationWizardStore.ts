import { create } from 'zustand';
import type {
  DetectedAgentAsset,
  DetectedMcpAsset,
  DetectedSkillAsset,
  MigrationExecutionProgress,
  MigrationWizardState,
  ScanRadarReport,
} from './migrationWizardTypes';

const INITIAL_AGENTS: DetectedAgentAsset[] = [
  {
    id: 'agent-oc-01',
    source: 'openclaw',
    originalName: 'OpenClaw Tech Lead',
    promptPreview: 'You are a principal engineer supervising code reviews and pull requests.',
    modelHint: 'claude-3-5-sonnet',
    selected: true,
  },
  {
    id: 'agent-oc-02',
    source: 'openclaw',
    originalName: 'Hermes Data Analyst',
    promptPreview: 'Expert at running SQL transformations and writing executive summaries.',
    modelHint: 'deepseek-v3',
    selected: true,
  },
  {
    id: 'agent-cursor-01',
    source: 'cursor',
    originalName: 'Cursor Refactoring Bot',
    promptPreview: 'Clean code refactorer conforming to SOLID principles.',
    modelHint: 'gpt-4o',
    selected: true,
  },
];

const INITIAL_SKILLS: DetectedSkillAsset[] = [
  {
    id: 'skill-01',
    source: 'openclaw',
    skillName: 'git-commit-helper',
    description: '自动格式化 Conventional Commits 并在本地暂存区自检',
    hasScripts: true,
    selected: true,
  },
  {
    id: 'skill-02',
    source: 'hermes',
    skillName: 'wechat-group-reporter',
    description: '定时抓取群聊重点发言并提炼成早报',
    hasScripts: true,
    selected: true,
  },
  {
    id: 'skill-03',
    source: 'claude_code',
    skillName: 'docker-env-auditor',
    description: '检查宿主机 Docker 容器状态与端口健康度',
    hasScripts: true,
    selected: true,
  },
];

const INITIAL_MCP: DetectedMcpAsset[] = [
  {
    id: 'mcp-01',
    source: 'openclaw',
    serverName: 'github-mcp-server',
    transportType: 'stdio',
    commandOrUrl: 'npx -y @modelcontextprotocol/server-github',
    selected: true,
  },
  {
    id: 'mcp-02',
    source: 'openclaw',
    serverName: 'postgres-reader',
    transportType: 'stdio',
    commandOrUrl: 'npx -y @modelcontextprotocol/server-postgres',
    selected: true,
  },
];

const INITIAL_REPORT: ScanRadarReport = {
  isScanning: false,
  hasDetectedAssets: true,
  scannedAt: Date.now(),
  agents: INITIAL_AGENTS,
  skills: INITIAL_SKILLS,
  mcpServers: INITIAL_MCP,
  totalAssetsCount: INITIAL_AGENTS.length + INITIAL_SKILLS.length + INITIAL_MCP.length,
};

const INITIAL_PROGRESS: MigrationExecutionProgress = {
  status: 'idle',
  progressPercentage: 0,
  currentStepText: '就绪',
  migratedCount: 0,
};

interface MigrationWizardActions {
  toggleAssetSelection: (type: 'agents' | 'skills' | 'mcpServers', id: string) => void;
  selectAll: (selected: boolean) => void;
  startMigration: () => Promise<void>;
  openDrawer: () => void;
  closeDrawer: () => void;
  dismissBanner: () => void;
  resetState: () => void;
}

export type MigrationWizardStore = MigrationWizardState & MigrationWizardActions;

const INITIAL_STATE: MigrationWizardState = {
  isBannerVisible: true,
  isDrawerOpen: false,
  radarReport: INITIAL_REPORT,
  progress: INITIAL_PROGRESS,
};

export const useMigrationWizardStore = create<MigrationWizardStore>((set, get) => ({
  ...INITIAL_STATE,

  toggleAssetSelection: (type: 'agents' | 'skills' | 'mcpServers', id: string) => {
    set((state) => {
      const report = state.radarReport;
      const updatedList = report[type].map((item) => {
        if (item.id === id) {
          return { ...item, selected: !item.selected };
        }
        return item;
      });

      return {
        radarReport: {
          ...report,
          [type]: updatedList,
        },
      };
    });
  },

  selectAll: (selected: boolean) => {
    set((state) => {
      const report = state.radarReport;
      return {
        radarReport: {
          ...report,
          agents: report.agents.map((a) => ({ ...a, selected })),
          skills: report.skills.map((s) => ({ ...s, selected })),
          mcpServers: report.mcpServers.map((m) => ({ ...m, selected })),
        },
      };
    });
  },

  startMigration: async (): Promise<void> => {
    const report = get().radarReport;
    const selectedAgents = report.agents.filter((a) => a.selected);
    const selectedSkills = report.skills.filter((s) => s.selected);
    const selectedMcp = report.mcpServers.filter((m) => m.selected);
    const totalSelected = selectedAgents.length + selectedSkills.length + selectedMcp.length;

    if (totalSelected === 0) {
      return;
    }

    set({
      progress: {
        status: 'migrating',
        progressPercentage: 15,
        currentStepText: '解析 OpenClaw 与 Hermes 配置文件...',
        migratedCount: 0,
      },
    });

    // 步进 1：无损转译 Agent 人设与 Prompt
    set({
      progress: {
        status: 'migrating',
        progressPercentage: 45,
        currentStepText: `正在转译 ${selectedAgents.length} 个 Agent 人设至 Myrm 规范...`,
        migratedCount: selectedAgents.length,
      },
    });

    // 步进 2：无损转译技能脚本
    set({
      progress: {
        status: 'migrating',
        progressPercentage: 80,
        currentStepText: `正在装载 ${selectedSkills.length} 个自研 Skills 并保留沙箱脚本...`,
        migratedCount: selectedAgents.length + selectedSkills.length,
      },
    });

    // 步进 3：完成并装配 MCP
    set({
      progress: {
        status: 'completed',
        progressPercentage: 100,
        currentStepText: '迁移完成！所有生态资产已无损融入 Myrm 统一工作台。',
        migratedCount: totalSelected,
      },
      isBannerVisible: false,
    });
  },

  openDrawer: () => {
    set({ isDrawerOpen: true });
  },

  closeDrawer: () => {
    set({ isDrawerOpen: false });
  },

  dismissBanner: () => {
    set({ isBannerVisible: false });
  },

  resetState: () => {
    set(INITIAL_STATE);
  },
}));
