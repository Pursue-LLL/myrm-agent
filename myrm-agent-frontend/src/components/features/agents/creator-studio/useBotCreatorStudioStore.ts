import { create } from 'zustand';
import type {
  BotCreatorFormValues,
  BotCreatorStudioState,
  CognitiveTier,
  CreatedBotSummary,
  InheritanceOptions,
  MasterAssetSnapshot,
  PixelMascot,
  TierMetadata,
} from './botCreatorStudioTypes';

export const COGNITIVE_TIERS: Record<CognitiveTier, TierMetadata> = {
  fast_flash: {
    tier: 'fast_flash',
    name: '轻量感知与分拣层 (Flash Tier)',
    badge: '高吞吐 / 超低成本',
    description: '适用于邮件过滤、社群消息清洗、快速意图分类与日常辅助任务',
    sampleModels: ['qwen-2.5-7b-instruct', 'gemini-1.5-flash', 'gpt-4o-mini'],
    costEfficiencyRatio: '成本仅为推理层的 1/15，毫秒级流式响应',
  },
  balanced_standard: {
    tier: 'balanced_standard',
    name: '通用平衡协作层 (Standard Tier)',
    badge: '标准主力模型',
    description: '适用于多轮通用对话、文档撰写、日常业务流程推进',
    sampleModels: ['deepseek-chat', 'claude-3-5-haiku', 'gpt-4o'],
    costEfficiencyRatio: '兼顾上下文理解力与响应速度的最佳性价比选择',
  },
  deep_reasoning: {
    tier: 'deep_reasoning',
    name: '深度推理与专家层 (Reasoning Tier)',
    badge: '强逻辑 / 长思维链',
    description: '适用于复杂代码重构、宏观研报撰写、复杂架构演进与数学推导',
    sampleModels: ['deepseek-reasoner', 'claude-3-7-sonnet', 'o3-mini'],
    costEfficiencyRatio: '投入更高算力换取极致严密逻辑与零死角排查',
  },
};

const DEFAULT_MASTER_ASSETS: MasterAssetSnapshot = {
  defaultModel: 'claude-3-7-sonnet',
  enabledTools: ['bash', 'read_file', 'browser', 'write_file'],
  enabledMcpServers: ['chrome-devtools', 'sqlite', 'sequential-thinking'],
  hasAuthCredentials: true,
};

const DEFAULT_PIXEL_MASCOTS: PixelMascot[] = [
  { id: 'mascot_cyber_cat', name: '赛博机甲猫', category: 'cyber', iconName: 'Cat', colorClass: 'text-amber-400' },
  { id: 'mascot_shiba_inu', name: '像素柴犬', category: 'pets', iconName: 'Dog', colorClass: 'text-yellow-400' },
  { id: 'mascot_mech_penguin', name: '机械小企鹅', category: 'pets', iconName: 'Bird', colorClass: 'text-sky-400' },
  { id: 'mascot_code_fox', name: '极客小狐狸', category: 'fantasy', iconName: 'Flame', colorClass: 'text-orange-400' },
  { id: 'mascot_cyber_bot', name: '哨兵机器人', category: 'cyber', iconName: 'Bot', colorClass: 'text-emerald-400' },
  { id: 'mascot_ghost_dragon', name: '星辉幼龙', category: 'fantasy', iconName: 'Sparkles', colorClass: 'text-purple-400' },
];

const INITIAL_FORM_VALUES: BotCreatorFormValues = {
  botName: '',
  roleDescription: '',
  soulPrompt: '你是一名世界顶级的专业助手，严格秉持第一性原理与高质量交付。',
  selectedTier: 'deep_reasoning',
  selectedModel: 'claude-3-7-sonnet',
  isInheritingMaster: true,
  inheritanceOptions: {
    inheritModel: true,
    inheritTools: true,
    inheritMcp: true,
    inheritCredentials: true,
  },
  avatarType: 'pixel_mascot',
  selectedMascotId: 'mascot_cyber_cat',
  aiAvatarPrompt: '',
  isGeneratingAvatar: false,
};

export const useBotCreatorStudioStore = create<BotCreatorStudioState>((set, get) => ({
  isOpen: false,
  form: INITIAL_FORM_VALUES,
  masterAssets: DEFAULT_MASTER_ASSETS,
  availableMascots: DEFAULT_PIXEL_MASCOTS,
  lastCreatedBot: null,

  openStudio: () => {
    set({
      isOpen: true,
      form: { ...INITIAL_FORM_VALUES },
    });
  },

  closeStudio: () => {
    set({ isOpen: false });
  },

  updateFormField: (field, value) => {
    set((state) => ({
      form: { ...state.form, [field]: value },
    }));
  },

  toggleInheritance: (enable: boolean) => {
    const { masterAssets } = get();
    set((state) => ({
      form: {
        ...state.form,
        isInheritingMaster: enable,
        selectedModel: enable ? masterAssets.defaultModel : state.form.selectedModel,
      },
    }));
  },

  toggleInheritanceOption: (option: keyof InheritanceOptions, enable: boolean) => {
    set((state) => ({
      form: {
        ...state.form,
        inheritanceOptions: {
          ...state.form.inheritanceOptions,
          [option]: enable,
        },
      },
    }));
  },

  selectCognitiveTier: (tier: CognitiveTier) => {
    const meta = COGNITIVE_TIERS[tier];
    const recommendedModel = meta.sampleModels[0];
    set((state) => ({
      form: {
        ...state.form,
        selectedTier: tier,
        selectedModel: state.form.isInheritingMaster
          ? state.form.selectedModel
          : recommendedModel,
      },
    }));
  },

  selectPixelMascot: (mascotId: string) => {
    set((state) => ({
      form: {
        ...state.form,
        selectedMascotId: mascotId,
        avatarType: 'pixel_mascot',
      },
    }));
  },

  generateAiAvatar: async () => {
    set((state) => ({
      form: { ...state.form, isGeneratingAvatar: true },
    }));

    await new Promise((resolve) => setTimeout(resolve, 350));

    const avatarUrl = `https://assets.myrm.ai/avatars/generated_${Date.now()}.png`;

    set((state) => ({
      form: {
        ...state.form,
        isGeneratingAvatar: false,
        avatarType: 'ai_generated',
        generatedAvatarUrl: avatarUrl,
      },
    }));
  },

  submitCreateBot: async () => {
    const { form, masterAssets } = get();
    const botId = `bot_${Date.now()}`;
    const summary: CreatedBotSummary = {
      id: botId,
      name: form.botName || '未命名智能体',
      role: form.roleDescription || '通用数字助理',
      model: form.selectedModel,
      tier: form.selectedTier,
      inheritedToolsCount: form.isInheritingMaster && form.inheritanceOptions.inheritTools
        ? masterAssets.enabledTools.length
        : 0,
      inheritedMcpCount: form.isInheritingMaster && form.inheritanceOptions.inheritMcp
        ? masterAssets.enabledMcpServers.length
        : 0,
      avatarSource: form.avatarType === 'pixel_mascot' ? form.selectedMascotId : (form.generatedAvatarUrl ?? 'default_icon'),
      createdAt: new Date().toISOString(),
    };

    set({
      lastCreatedBot: summary,
      isOpen: false,
    });

    return summary;
  },

  resetStudioForm: () => {
    set({
      form: { ...INITIAL_FORM_VALUES },
      lastCreatedBot: null,
    });
  },
}));
