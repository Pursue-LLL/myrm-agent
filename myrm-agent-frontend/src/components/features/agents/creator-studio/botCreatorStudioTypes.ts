export type CognitiveTier = 'fast_flash' | 'balanced_standard' | 'deep_reasoning';

export interface TierMetadata {
  tier: CognitiveTier;
  name: string;
  badge: string;
  description: string;
  sampleModels: string[];
  costEfficiencyRatio: string;
}

export interface MasterAssetSnapshot {
  defaultModel: string;
  enabledTools: string[];
  enabledMcpServers: string[];
  hasAuthCredentials: boolean;
}

export interface InheritanceOptions {
  inheritModel: boolean;
  inheritTools: boolean;
  inheritMcp: boolean;
  inheritCredentials: boolean;
}

export interface PixelMascot {
  id: string;
  name: string;
  category: 'pets' | 'cyber' | 'fantasy';
  iconName: string;
  colorClass: string;
}

export type AvatarSourceType = 'pixel_mascot' | 'ai_generated';

export interface BotCreatorFormValues {
  botName: string;
  roleDescription: string;
  soulPrompt: string;
  selectedTier: CognitiveTier;
  selectedModel: string;
  isInheritingMaster: boolean;
  inheritanceOptions: InheritanceOptions;
  avatarType: AvatarSourceType;
  selectedMascotId: string;
  aiAvatarPrompt: string;
  isGeneratingAvatar: boolean;
  generatedAvatarUrl?: string;
}

export interface CreatedBotSummary {
  id: string;
  name: string;
  role: string;
  model: string;
  tier: CognitiveTier;
  inheritedToolsCount: number;
  inheritedMcpCount: number;
  avatarSource: string;
  createdAt: string;
}

export interface BotCreatorStudioState {
  isOpen: boolean;
  form: BotCreatorFormValues;
  masterAssets: MasterAssetSnapshot;
  availableMascots: PixelMascot[];
  lastCreatedBot: CreatedBotSummary | null;

  openStudio: () => void;
  closeStudio: () => void;
  updateFormField: <K extends keyof BotCreatorFormValues>(field: K, value: BotCreatorFormValues[K]) => void;
  toggleInheritance: (enable: boolean) => void;
  toggleInheritanceOption: (option: keyof InheritanceOptions, enable: boolean) => void;
  selectCognitiveTier: (tier: CognitiveTier) => void;
  selectPixelMascot: (mascotId: string) => void;
  generateAiAvatar: () => Promise<void>;
  submitCreateBot: () => Promise<CreatedBotSummary>;
  resetStudioForm: () => void;
}
