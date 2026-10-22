import { create } from 'zustand';
import {
  parseNaturalLanguageConfigIntent,
  validateConfigParams,
} from './conversationalConfigEngine';
import {
  ConversationalConfigIntent,
  NonDevWizardStep,
} from './conversationalConfigTypes';

interface ConversationalConfigState {
  activeConfigCards: Record<string, ConversationalConfigIntent>;
  isNonDevWizardOpen: boolean;
  wizardCurrentStep: number;
  appliedConfigurations: Record<string, string>;

  triggerConfigIntent: (utterance: string) => string | null;
  addConfigCard: (card: ConversationalConfigIntent) => void;
  updateCardParamValue: (
    cardId: string,
    paramKey: string,
    value: string,
  ) => void;
  applyConfiguration: (cardId: string) => boolean;
  dismissConfigCard: (cardId: string) => void;
  toggleNonDevWizard: (open?: boolean) => void;
  setWizardStep: (step: number) => void;
  reset: () => void;
}

export const NON_DEV_WIZARD_STEPS: NonDevWizardStep[] = [
  {
    stepNumber: 1,
    title: '选择您的核心工作场景',
    subtitle: 'Myrm 将根据您的偏好自动定制首页与预设提示词',
    options: [
      {
        id: 'office',
        label: '通用办公与研报发票',
        desc: '发票整理、合同审查、会议纪要与公文润色',
        icon: 'briefcase',
      },
      {
        id: 'coding',
        label: '极客研发与代码工程',
        desc: '架构重构、自动化单测、沙箱编译与部署',
        icon: 'code',
      },
      {
        id: 'creative',
        label: '多媒体设计与自媒体排期',
        desc: '图文海报、视频脚本与全渠道分发排期',
        icon: 'palette',
      },
    ],
  },
  {
    stepNumber: 2,
    title: '选择首选大模型接入方式',
    subtitle: '零繁琐配置，只需点选即可瞬间激活',
    options: [
      {
        id: 'cloud_free',
        label: '官方预置极速云端通道',
        desc: '开箱即用，免配置 API Key，秒速响应',
        icon: 'zap',
      },
      {
        id: 'custom_key',
        label: '自备 API Key 私有接入',
        desc: '支持 OpenAI、Anthropic、DeepSeek 等原生授权',
        icon: 'key',
      },
      {
        id: 'local_ollama',
        label: '本地 Ollama / 本机模型',
        desc: '100% 离线隐私数据不离身，零费用支出',
        icon: 'cpu',
      },
    ],
  },
  {
    stepNumber: 3,
    title: '准备就绪，开启首个任务',
    subtitle: '像老朋友一样在对话框输入自然语言即可协同',
    options: [
      {
        id: 'start_invoice',
        label: '尝试：帮我整理发票文件夹',
        desc: '自动 OCR 并导出 Excel 报销明细表',
        icon: 'file-spreadsheet',
      },
      {
        id: 'start_chat',
        label: '直接开启自由探索对话',
        desc: '随时随地输入任意问题与指令',
        icon: 'message-square',
      },
    ],
  },
];

export const useConversationalConfigStore = create<ConversationalConfigState>(
  (set, get) => ({
    activeConfigCards: {},
    isNonDevWizardOpen: false,
    wizardCurrentStep: 1,
    appliedConfigurations: {
      model_name: 'claude-3-7-sonnet',
      search_engine: 'tavily',
    },

    triggerConfigIntent: (utterance: string): string | null => {
      const parsed = parseNaturalLanguageConfigIntent(utterance);
      if (!parsed) {
        return null;
      }

      set((state) => ({
        activeConfigCards: {
          ...state.activeConfigCards,
          [parsed.id]: parsed,
        },
      }));

      return parsed.id;
    },

    addConfigCard: (card: ConversationalConfigIntent): void => {
      set((state) => ({
        activeConfigCards: {
          ...state.activeConfigCards,
          [card.id]: card,
        },
      }));
    },

    updateCardParamValue: (
      cardId: string,
      paramKey: string,
      value: string,
    ): void => {
      set((state) => {
        const target = state.activeConfigCards[cardId];
        if (!target) {
          return state;
        }

        const updatedParams = target.params.map((p) => {
          if (p.key === paramKey) {
            return { ...p, value };
          }
          return p;
        });

        return {
          activeConfigCards: {
            ...state.activeConfigCards,
            [cardId]: {
              ...target,
              params: updatedParams,
            },
          },
        };
      });
    },

    applyConfiguration: (cardId: string): boolean => {
      const target = get().activeConfigCards[cardId];
      if (!target || target.isApplied) {
        return false;
      }

      const validation = validateConfigParams(target.params);
      if (!validation.valid) {
        return false;
      }

      const newConfigs = { ...get().appliedConfigurations };
      for (const p of target.params) {
        if (p.value) {
          newConfigs[p.key] = p.value;
        }
      }

      set((state) => ({
        appliedConfigurations: newConfigs,
        activeConfigCards: {
          ...state.activeConfigCards,
          [cardId]: {
            ...target,
            isApplied: true,
          },
        },
      }));

      return true;
    },

    dismissConfigCard: (cardId: string): void => {
      set((state) => {
        const next = { ...state.activeConfigCards };
        delete next[cardId];
        return { activeConfigCards: next };
      });
    },

    toggleNonDevWizard: (open?: boolean): void => {
      set((state) => ({
        isNonDevWizardOpen:
          open !== undefined ? open : !state.isNonDevWizardOpen,
      }));
    },

    setWizardStep: (step: number): void => {
      set({ wizardCurrentStep: Math.max(1, Math.min(3, step)) });
    },

    reset: (): void => {
      set({
        activeConfigCards: {},
        isNonDevWizardOpen: false,
        wizardCurrentStep: 1,
        appliedConfigurations: {
          model_name: 'claude-3-7-sonnet',
          search_engine: 'tavily',
        },
      });
    },
  }),
);
