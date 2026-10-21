export type OnboardingStep =
  | 'greeting'
  | 'intent_selection'
  | 'recipe_preview'
  | 'completed';

export type AgentDomainPreset =
  | 'marketing'
  | 'software_eng'
  | 'admin_writing'
  | 'finance_audit'
  | 'custom';

export interface RecommendedSkill {
  id: string;
  name: string;
  category: string;
  description: string;
  selected: boolean;
}

export interface AgentRecipeDraft {
  presetKey: AgentDomainPreset;
  suggestedName: string;
  roleTitle: string;
  description: string;
  systemPrompt: string;
  recommendedSkills: RecommendedSkill[];
  recommendedModelTier: 'turbo' | 'pro';
  estimatedTokenSavingPct: number;
}

export interface WizardChatMessage {
  id: string;
  sender: 'assistant' | 'user';
  text: string;
  timestampMs: number;
  interactiveOptions?: Array<{
    label: string;
    presetKey: AgentDomainPreset;
    description: string;
  }>;
}

export interface LauncherServiceStatus {
  id: string;
  name: string;
  isReady: boolean;
  latencyMs: number;
  details: string;
}
