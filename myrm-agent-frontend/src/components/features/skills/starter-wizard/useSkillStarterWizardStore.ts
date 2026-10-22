import { create } from 'zustand';
import type {
  SkillStarterPreset,
  SkillStarterWizardState,
  SniffedResource,
  TrialRunResult,
  CronHostingBlueprint,
} from './starterWizardTypes';

export const STARTER_PRESETS: Record<string, SkillStarterPreset> = {
  wechat_group_summary: {
    skillId: 'wechat_group_summary',
    skillName: '微信群聊晨报生成器',
    category: '办公协作与社群运营',
    description: '受控读取指定本地微信群聊天记录，每天早晨自动提取精华提要并推送至选定渠道。',
    defaultCronExpression: '0 8 * * *',
    defaultCronHumanText: '每天早上 08:00',
    parameters: [
      {
        key: 'target_group',
        label: '目标群聊',
        type: 'sniffer_select',
        description: '自动嗅探本地微信活跃群组，免手动输入',
        required: true,
        snifferType: 'wechat_groups',
      },
      {
        key: 'time_window',
        label: '分析时间窗口',
        type: 'time_window',
        description: '需要提炼的历史消息范围',
        required: true,
        defaultValue: 'yesterday_full_day',
        options: [
          { value: 'yesterday_full_day', label: '昨日全天 (00:00 - 24:00)' },
          { value: 'last_24_hours', label: '最近 24 小时' },
          { value: 'last_3_days', label: '最近 3 天深度复盘' },
        ],
      },
      {
        key: 'business_perspective',
        label: '业务视角',
        type: 'select',
        description: '模型提炼的核心侧重点',
        required: true,
        defaultValue: 'owner_governance',
        options: [
          { value: 'owner_governance', label: '群主治理（舆情风向与违规预警）' },
          { value: 'instructor_teaching', label: '讲师教学（高频提问与疑难答疑）' },
          { value: 'sales_leads', label: '销售线索（商机识别与采购意向）' },
          { value: 'knowledge_digest', label: '普通干货（行业动态与精选链接）' },
        ],
      },
    ],
  },
  github_daily_digest: {
    skillId: 'github_daily_digest',
    skillName: 'GitHub 仓库动向每日速览',
    category: '研发效能与开源跟踪',
    description: '自动跟踪本地或重点关注的 Git 仓库最新 PR、Issue 与 Release 并生成结构化日报。',
    defaultCronExpression: '30 9 * * 1-5',
    defaultCronHumanText: '工作日每天 09:30',
    parameters: [
      {
        key: 'target_repo',
        label: '目标代码仓',
        type: 'sniffer_select',
        description: '自动嗅探本地研发工作区代码仓',
        required: true,
        snifferType: 'git_repos',
      },
      {
        key: 'filter_scope',
        label: '重点过滤范围',
        type: 'select',
        description: '日报关注的重点动向',
        required: true,
        defaultValue: 'prs_and_releases',
        options: [
          { value: 'prs_and_releases', label: 'PR 合并与 Release 发布' },
          { value: 'critical_issues', label: '高优先级与未解决 Issue' },
          { value: 'full_activity', label: '全量提交与代码审查记录' },
        ],
      },
    ],
  },
};

const DEFAULT_SNIFFED_RESOURCES: Record<string, SniffedResource[]> = {
  wechat_groups: [
    {
      id: 'wx_grp_ai_frontier',
      name: 'AI 前沿落地与企业内测群',
      type: 'wechat_groups',
      memberCount: 482,
      lastActiveTime: '3 分钟前',
      isRecommended: true,
    },
    {
      id: 'wx_grp_fullstack_dev',
      name: '全栈架构师深度交流会',
      type: 'wechat_groups',
      memberCount: 318,
      lastActiveTime: '12 分钟前',
    },
    {
      id: 'wx_grp_prod_feedback',
      name: 'Myrm 核心天使用户反馈专区',
      type: 'wechat_groups',
      memberCount: 156,
      lastActiveTime: '25 分钟前',
    },
  ],
  git_repos: [
    {
      id: 'repo_open_perplexity',
      name: 'open-perplexity / main',
      type: 'git_repos',
      memberCount: 14,
      lastActiveTime: '刚刚',
      isRecommended: true,
    },
    {
      id: 'repo_myrm_core',
      name: 'myrm-agent-core / staging',
      type: 'git_repos',
      memberCount: 8,
      lastActiveTime: '1 小时前',
    },
  ],
};

const INITIAL_TRIAL_RUN: TrialRunResult = {
  status: 'idle',
};

const INITIAL_CRON_BLUEPRINT: CronHostingBlueprint = {
  cronExpression: '0 8 * * *',
  humanReadableTime: '每天早上 08:00',
  isEnabled: false,
  targetChannel: 'chat',
};

export const useSkillStarterWizardStore = create<SkillStarterWizardState>((set, get) => ({
  isOpen: false,
  activeSkill: null,
  formValues: {},
  sniffedResources: [],
  isSniffing: false,
  selectedResourceId: '',
  trialRun: INITIAL_TRIAL_RUN,
  cronBlueprint: INITIAL_CRON_BLUEPRINT,

  openWizard: (skillId: string) => {
    const preset = STARTER_PRESETS[skillId] ?? STARTER_PRESETS.wechat_group_summary;
    const initialForm: Record<string, string> = {};
    for (const param of preset.parameters) {
      if (param.defaultValue) {
        initialForm[param.key] = param.defaultValue;
      }
    }

    const snifferType = preset.parameters.find((p) => p.type === 'sniffer_select')?.snifferType ?? 'wechat_groups';
    const resources = DEFAULT_SNIFFED_RESOURCES[snifferType] ?? [];
    const firstResourceId = resources[0]?.id ?? '';

    if (firstResourceId) {
      initialForm[preset.parameters[0].key] = firstResourceId;
    }

    set({
      isOpen: true,
      activeSkill: preset,
      formValues: initialForm,
      sniffedResources: resources,
      selectedResourceId: firstResourceId,
      trialRun: { status: 'idle' },
      cronBlueprint: {
        cronExpression: preset.defaultCronExpression,
        humanReadableTime: preset.defaultCronHumanText,
        isEnabled: false,
        targetChannel: 'chat',
      },
    });
  },

  closeWizard: () => {
    set({ isOpen: false });
  },

  setFormValue: (key: string, value: string) => {
    set((state) => ({
      formValues: { ...state.formValues, [key]: value },
    }));
  },

  selectResource: (resourceId: string) => {
    const { activeSkill } = get();
    const primaryKey = activeSkill?.parameters[0]?.key ?? 'target_group';
    set((state) => ({
      selectedResourceId: resourceId,
      formValues: { ...state.formValues, [primaryKey]: resourceId },
    }));
  },

  refreshSniffer: async () => {
    set({ isSniffing: true });
    await new Promise((resolve) => setTimeout(resolve, 300));
    const { activeSkill } = get();
    const snifferType = activeSkill?.parameters.find((p) => p.type === 'sniffer_select')?.snifferType ?? 'wechat_groups';
    const refreshed = DEFAULT_SNIFFED_RESOURCES[snifferType] ?? [];
    set({
      sniffedResources: refreshed,
      isSniffing: false,
    });
  },

  executeTrialRun: async () => {
    const { activeSkill, formValues, sniffedResources, selectedResourceId } = get();
    if (!activeSkill) {
      return;
    }

    set({ trialRun: { status: 'running' } });

    await new Promise((resolve) => setTimeout(resolve, 350));

    const selectedResource = sniffedResources.find((r) => r.id === selectedResourceId);
    const resourceName = selectedResource ? selectedResource.name : '选定目标';
    const perspective = formValues.business_perspective ?? '默认视角';
    const timeWindow = formValues.time_window ?? '昨日全天';

    const sampleSummary = `【${activeSkill.skillName} · 试跑产物预览】\n` +
      `📌 分析目标：${resourceName}\n` +
      `⏱ 时间窗口：${timeWindow}\n` +
      `🔍 业务视角：${perspective}\n` +
      `----------------------------------------\n` +
      `1. 昨日累计汇总重要互动 142 条，核心高频词包含“性能调优”、“模型幻觉”、“离线调度”；\n` +
      `2. 识别出 3 个高价值讨论主题，未发现敏感违规言论；\n` +
      `3. 提炼出 2 个待跟进问题已自动建立待办。`;

    set({
      trialRun: {
        status: 'success',
        summaryPreview: sampleSummary,
        extractedItemsCount: 142,
        executionDurationMs: 350,
        executedPrompt: `针对 ${resourceName} 执行 ${perspective} 提炼`,
      },
    });
  },

  toggleCronHosting: async (enable: boolean) => {
    const { cronBlueprint } = get();
    if (enable) {
      const jobId = `cron_job_${Date.now()}`;
      set({
        cronBlueprint: {
          ...cronBlueprint,
          isEnabled: true,
          scheduledJobId: jobId,
          lastActivatedAt: new Date().toISOString(),
        },
      });
    } else {
      set({
        cronBlueprint: {
          ...cronBlueprint,
          isEnabled: false,
          scheduledJobId: undefined,
        },
      });
    }
  },

  updateTargetChannel: (channel: 'chat' | 'desktop_notification' | 'webhook') => {
    set((state) => ({
      cronBlueprint: {
        ...state.cronBlueprint,
        targetChannel: channel,
      },
    }));
  },

  resetWizardState: () => {
    set({
      isOpen: false,
      activeSkill: null,
      formValues: {},
      sniffedResources: [],
      isSniffing: false,
      selectedResourceId: '',
      trialRun: INITIAL_TRIAL_RUN,
      cronBlueprint: INITIAL_CRON_BLUEPRINT,
    });
  },
}));
