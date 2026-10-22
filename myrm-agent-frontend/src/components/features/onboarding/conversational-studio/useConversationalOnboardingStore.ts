import { create } from 'zustand';
import {
  OnboardingStep,
  AgentDomainPreset,
  AgentRecipeDraft,
  WizardChatMessage,
  LauncherServiceStatus,
} from './conversationalOnboardingTypes';
import {
  getRecipeByPreset,
  inferRecipeFromUserInput,
} from './conversationalInferenceEngine';

export interface ConversationalOnboardingState {
  step: OnboardingStep;
  messages: WizardChatMessage[];
  activeRecipeDraft: AgentRecipeDraft | null;
  launcherServices: LauncherServiceStatus[];
  isCompleted: boolean;
  customInputText: string;

  // Actions
  setCustomInputText: (text: string) => void;
  selectPresetIntent: (presetKey: AgentDomainPreset) => void;
  submitUserInput: (text: string) => void;
  toggleSkillSelection: (skillId: string) => void;
  updateRecipeDraft: (patch: Partial<AgentRecipeDraft>) => void;
  applyRecipeAndComplete: () => { success: boolean; createdAgentId: string };
  resetOnboarding: () => void;
}

const INITIAL_MESSAGES: WizardChatMessage[] = [
  {
    id: 'msg_welcome_1',
    sender: 'assistant',
    text: '嗨！我是您的 AI 全能协作成长伙伴。今天主要想让我协助您做哪方面的工作？您可以直接点击下方卡片，或直接用一句话告诉我您的日常需求。',
    timestampMs: Date.now(),
    interactiveOptions: [
      {
        label: '代码架构与工程',
        presetKey: 'software_eng',
        description: '重构、全栈开发、Git 自动化与单测',
      },
      {
        label: '营销与竞品洞察',
        presetKey: 'marketing',
        description: '网页抓取、社交舆情与增长看板',
      },
      {
        label: '行政与高效写作',
        presetKey: 'admin_writing',
        description: '会议纪要提取、公文格式化与待办',
      },
      {
        label: '财务对账与审计',
        presetKey: 'finance_audit',
        description: '报销验真、多表函数核对与发票提取',
      },
    ],
  },
];

const DEFAULT_LAUNCHER_SERVICES: LauncherServiceStatus[] = [
  {
    id: 'svc_webui',
    name: '图形化 Web 工作台',
    isReady: true,
    latencyMs: 1,
    details: 'React 19 + Tailwind 极速渲染',
  },
  {
    id: 'svc_sandbox',
    name: '原生隔离执行环境',
    isReady: true,
    latencyMs: 3,
    details: 'Zero-CLI 安全虚拟化沙箱',
  },
  {
    id: 'svc_ai_models',
    name: '智能模型路由通道',
    isReady: true,
    latencyMs: 18,
    details: 'Turbo / Pro 双档算力直连',
  },
];

export const useConversationalOnboardingStore = create<ConversationalOnboardingState>(
  (set, get) => ({
    step: 'intent_selection',
    messages: INITIAL_MESSAGES,
    activeRecipeDraft: null,
    launcherServices: DEFAULT_LAUNCHER_SERVICES,
    isCompleted: false,
    customInputText: '',

    setCustomInputText: (text: string) => {
      set({ customInputText: text });
    },

    selectPresetIntent: (presetKey: AgentDomainPreset) => {
      const recipe = getRecipeByPreset(presetKey);
      const userMsg: WizardChatMessage = {
        id: `msg_user_${Date.now()}`,
        sender: 'user',
        text: `我选择：${recipe.suggestedName} (${recipe.roleTitle})`,
        timestampMs: Date.now(),
      };
      const assistantMsg: WizardChatMessage = {
        id: `msg_assistant_${Date.now() + 1}`,
        sender: 'assistant',
        text: `太棒了！已为您推导出「${recipe.suggestedName}」的最佳专属配方。右侧已自动勾选推荐技能与推荐算力，您可以按需微调，点击即可直接生效！`,
        timestampMs: Date.now() + 1,
      };

      set((state) => ({
        step: 'recipe_preview',
        activeRecipeDraft: recipe,
        messages: [...state.messages, userMsg, assistantMsg],
      }));
    },

    submitUserInput: (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) {
        return;
      }

      const recipe = inferRecipeFromUserInput(trimmed);
      const userMsg: WizardChatMessage = {
        id: `msg_user_${Date.now()}`,
        sender: 'user',
        text: trimmed,
        timestampMs: Date.now(),
      };
      const assistantMsg: WizardChatMessage = {
        id: `msg_assistant_${Date.now() + 1}`,
        sender: 'assistant',
        text: `已根据您的需求「${trimmed.slice(0, 30)}...」，智能推导并定制了「${recipe.suggestedName}」。专属提示词与关联技能已就绪！`,
        timestampMs: Date.now() + 1,
      };

      set((state) => ({
        step: 'recipe_preview',
        activeRecipeDraft: recipe,
        customInputText: '',
        messages: [...state.messages, userMsg, assistantMsg],
      }));
    },

    toggleSkillSelection: (skillId: string) => {
      const current = get().activeRecipeDraft;
      if (!current) {
        return;
      }

      const updatedSkills = current.recommendedSkills.map((s) => {
        if (s.id !== skillId) {
          return s;
        }
        return { ...s, selected: !s.selected };
      });

      set({
        activeRecipeDraft: {
          ...current,
          recommendedSkills: updatedSkills,
        },
      });
    },

    updateRecipeDraft: (patch: Partial<AgentRecipeDraft>) => {
      const current = get().activeRecipeDraft;
      if (!current) {
        return;
      }
      set({
        activeRecipeDraft: {
          ...current,
          ...patch,
        },
      });
    },

    applyRecipeAndComplete: () => {
      const draft = get().activeRecipeDraft;
      const createdAgentId = `agent_onboarded_${Date.now()}`;
      set({
        step: 'completed',
        isCompleted: true,
      });
      return {
        success: Boolean(draft),
        createdAgentId,
      };
    },

    resetOnboarding: () => {
      set({
        step: 'intent_selection',
        messages: INITIAL_MESSAGES,
        activeRecipeDraft: null,
        launcherServices: DEFAULT_LAUNCHER_SERVICES,
        isCompleted: false,
        customInputText: '',
      });
    },
  })
);
