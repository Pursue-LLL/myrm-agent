export type SnifferResourceType = 'wechat_groups' | 'git_repos' | 'slack_channels';

export interface SniffedResource {
  id: string;
  name: string;
  type: SnifferResourceType;
  memberCount?: number;
  lastActiveTime?: string;
  isRecommended?: boolean;
}

export type WizardParameterType = 'sniffer_select' | 'select' | 'text' | 'time_window';

export interface ParameterOption {
  value: string;
  label: string;
  description?: string;
}

export interface ParameterSchema {
  key: string;
  label: string;
  type: WizardParameterType;
  description: string;
  required: boolean;
  defaultValue?: string;
  options?: ParameterOption[];
  snifferType?: SnifferResourceType;
}

export interface SkillStarterPreset {
  skillId: string;
  skillName: string;
  category: string;
  description: string;
  parameters: ParameterSchema[];
  defaultCronExpression: string;
  defaultCronHumanText: string;
}

export type TrialRunStatus = 'idle' | 'running' | 'success' | 'failed';

export interface TrialRunResult {
  status: TrialRunStatus;
  summaryPreview?: string;
  extractedItemsCount?: number;
  executionDurationMs?: number;
  errorMessage?: string;
  executedPrompt?: string;
}

export interface CronHostingBlueprint {
  cronExpression: string;
  humanReadableTime: string;
  isEnabled: boolean;
  targetChannel: 'chat' | 'desktop_notification' | 'webhook';
  scheduledJobId?: string;
  lastActivatedAt?: string;
}

export interface SkillStarterWizardState {
  isOpen: boolean;
  activeSkill: SkillStarterPreset | null;
  formValues: Record<string, string>;
  sniffedResources: SniffedResource[];
  isSniffing: boolean;
  selectedResourceId: string;
  trialRun: TrialRunResult;
  cronBlueprint: CronHostingBlueprint;
  
  openWizard: (skillId: string) => void;
  closeWizard: () => void;
  setFormValue: (key: string, value: string) => void;
  selectResource: (resourceId: string) => void;
  refreshSniffer: () => Promise<void>;
  executeTrialRun: () => Promise<void>;
  toggleCronHosting: (enable: boolean) => Promise<void>;
  updateTargetChannel: (channel: 'chat' | 'desktop_notification' | 'webhook') => void;
  resetWizardState: () => void;
}
