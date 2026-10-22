export type BotActivityType = 'idle' | 'active_cron' | 'active_tool_exec' | 'active_thinking';

export interface BotPulseStatus {
  isActive: boolean;
  activityType: BotActivityType;
  currentTaskTitle?: string;
  startedAt?: string;
  progressPercent?: number;
}

export interface BotCronJob {
  id: string;
  title: string;
  cronExpression: string;
  isEnabled: boolean;
  lastRunTime?: string;
  lastStatus?: 'success' | 'failed' | 'running';
}

export interface BotProfile {
  id: string;
  name: string;
  role: string;
  avatarIconName?: string;
  pulse: BotPulseStatus;
  cronJobs: BotCronJob[];
  latestOutputSummary?: string;
}

export type CockpitPaneMode = 'two_pane' | 'three_pane' | 'four_pane';

export interface MultiPaneCockpitState {
  paneMode: CockpitPaneMode;
  selectedBotId: string;
  bots: BotProfile[];
  isRosterCollapsed: boolean;
  isCronInspectorOpen: boolean;
  isArtifactInspectorOpen: boolean;
  activeHandoffBotId: string | null;

  setPaneMode: (mode: CockpitPaneMode) => void;
  selectBot: (botId: string) => void;
  toggleRosterCollapse: () => void;
  toggleCronInspector: (open?: boolean) => void;
  toggleArtifactInspector: (open?: boolean) => void;
  triggerBotPulse: (botId: string, pulse: BotPulseStatus) => void;
  toggleBotCronJob: (botId: string, cronId: string, enable: boolean) => void;
  handoffToBotSession: (botId: string) => void;
  resetCockpitState: () => void;
}
