import { create } from 'zustand';
import type {
  BotProfile,
  BotPulseStatus,
  CockpitPaneMode,
  MultiPaneCockpitState,
} from './multiPaneCockpitTypes';

const INITIAL_BOTS: BotProfile[] = [
  {
    id: 'bot_morning_wechat',
    name: '晨报速递管家',
    role: '社群运营与每日群聊精华提炼',
    avatarIconName: 'MessageSquare',
    pulse: {
      isActive: true,
      activityType: 'active_cron',
      currentTaskTitle: '正在执行每日微信群 08:00 定时摘要提炼...',
      progressPercent: 78,
    },
    cronJobs: [
      {
        id: 'cron_wechat_morning',
        title: '每日早上 08:00 群聊晨报',
        cronExpression: '0 8 * * *',
        isEnabled: true,
        lastRunTime: '今日 08:00',
        lastStatus: 'success',
      },
      {
        id: 'cron_wechat_evening',
        title: '工作日 18:30 晚间复盘',
        cronExpression: '30 18 * * 1-5',
        isEnabled: false,
      },
    ],
    latestOutputSummary: '今日已完成 482 条社群互动提取，识别出 3 个高价值讨论主题。',
  },
  {
    id: 'bot_deep_researcher',
    name: '深度研报学者',
    role: '全网宏观调研与多维论文对比',
    avatarIconName: 'BookOpen',
    pulse: {
      isActive: true,
      activityType: 'active_thinking',
      currentTaskTitle: '思维链推理中：对比 Transformer 与 Mamba 架构延时特性',
      progressPercent: 45,
    },
    cronJobs: [
      {
        id: 'cron_arxiv_daily',
        title: 'Arxiv 每日 AI 重点论文跟踪',
        cronExpression: '0 9 * * *',
        isEnabled: true,
        lastRunTime: '昨日 09:00',
        lastStatus: 'success',
      },
    ],
    latestOutputSummary: '正在解析注意力机制矩阵稀疏化，已检索 14 篇最新顶会论文。',
  },
  {
    id: 'bot_code_auditor',
    name: '代码安全守卫',
    role: 'AST 语法静态检查与漏洞红线门禁',
    avatarIconName: 'Shield',
    pulse: {
      isActive: false,
      activityType: 'idle',
    },
    cronJobs: [
      {
        id: 'cron_nightly_lint',
        title: '每夜全仓 Lint & 依赖扫描',
        cronExpression: '0 2 * * *',
        isEnabled: true,
        lastRunTime: '今日 02:00',
        lastStatus: 'success',
      },
    ],
    latestOutputSummary: '昨夜完成 32 个包的依赖合规性扫描，零高危漏洞。',
  },
  {
    id: 'bot_growth_hacker',
    name: '增长策略分析师',
    role: '转化漏斗分析与 A/B 实验追踪',
    avatarIconName: 'TrendingUp',
    pulse: {
      isActive: false,
      activityType: 'idle',
    },
    cronJobs: [],
    latestOutputSummary: '上周用户留存率环比上升 4.2%，活跃留存表现良好。',
  },
];

export const useMultiPaneCockpitStore = create<MultiPaneCockpitState>((set) => ({
  paneMode: 'three_pane',
  selectedBotId: 'bot_morning_wechat',
  bots: INITIAL_BOTS,
  isRosterCollapsed: false,
  isCronInspectorOpen: true,
  isArtifactInspectorOpen: false,
  activeHandoffBotId: null,

  setPaneMode: (mode: CockpitPaneMode) => {
    set({
      paneMode: mode,
      isCronInspectorOpen: mode !== 'two_pane',
      isArtifactInspectorOpen: mode === 'four_pane',
    });
  },

  selectBot: (botId: string) => {
    set({ selectedBotId: botId });
  },

  toggleRosterCollapse: () => {
    set((state) => ({ isRosterCollapsed: !state.isRosterCollapsed }));
  },

  toggleCronInspector: (open?: boolean) => {
    set((state) => ({
      isCronInspectorOpen: open !== undefined ? open : !state.isCronInspectorOpen,
    }));
  },

  toggleArtifactInspector: (open?: boolean) => {
    set((state) => ({
      isArtifactInspectorOpen: open !== undefined ? open : !state.isArtifactInspectorOpen,
    }));
  },

  triggerBotPulse: (botId: string, pulse: BotPulseStatus) => {
    set((state) => ({
      bots: state.bots.map((bot) => {
        if (bot.id === botId) {
          return { ...bot, pulse };
        }
        return bot;
      }),
    }));
  },

  toggleBotCronJob: (botId: string, cronId: string, enable: boolean) => {
    set((state) => ({
      bots: state.bots.map((bot) => {
        if (bot.id === botId) {
          return {
            ...bot,
            cronJobs: bot.cronJobs.map((job) => {
              if (job.id === cronId) {
                return { ...job, isEnabled: enable };
              }
              return job;
            }),
          };
        }
        return bot;
      }),
    }));
  },

  handoffToBotSession: (botId: string) => {
    set({
      selectedBotId: botId,
      activeHandoffBotId: botId,
    });
  },

  resetCockpitState: () => {
    set({
      paneMode: 'three_pane',
      selectedBotId: 'bot_morning_wechat',
      bots: INITIAL_BOTS,
      isRosterCollapsed: false,
      isCronInspectorOpen: true,
      isArtifactInspectorOpen: false,
      activeHandoffBotId: null,
    });
  },
}));
