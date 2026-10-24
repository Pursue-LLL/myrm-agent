export type VerticalRoleCategory =
  | 'life_admin'
  | 'office_manager'
  | 'clipper'
  | 'chief_of_staff'
  | 'sales_team';

export type ReasoningEffort = 'low' | 'medium' | 'high';

export interface VerticalRolePresetItem {
  roleId: string;
  category: VerticalRoleCategory;
  displayName: string;
  description: string;
  personaPrompt: string;
  recommendedSkills: string[];
  recommendedTools: string[];
  reasoningEffort: ReasoningEffort;
  typicalTasks: string[];
}

export interface SubBotTestRequestItem {
  roleId: string;
  testPrompt: string;
  mockInputs?: Record<string, string>;
  timeoutSeconds?: number;
}

export interface SubBotTestResultItem {
  testId: string;
  roleId: string;
  success: boolean;
  outputText: string;
  toolCallsMade: string[];
  executionTimeMs: number;
  logs: string[];
  errorMessage?: string | null;
}

export interface AgentFlowStepItem {
  stepId: string;
  sourceAgentId: string;
  targetAgentId: string;
  action: string;
  payloadSummary: string;
  resultSummary?: string;
  durationMs: number;
  timestamp: number;
}

export interface AgentFlowTraceItem {
  traceId: string;
  sessionId: string;
  rootAgentId: string;
  steps: AgentFlowStepItem[];
  totalDurationMs: number;
  isLoopDetected: boolean;
}

export interface VerticalPresetsAndSandboxCardProps {
  sessionId?: string;
  initialPresets?: VerticalRolePresetItem[];
  onDismiss?: () => void;
  onRunSandboxTest?: (result: SubBotTestResultItem) => void;
}

export const INITIAL_VERTICAL_PRESETS: VerticalRolePresetItem[] = [
  {
    roleId: 'life_admin',
    category: 'life_admin',
    displayName: 'Life Admin Specialist',
    description: 'Personal assistant for schedule coordination, habit tracking, and travel logistics.',
    personaPrompt: 'You are an empathetic, ultra-organized Life Admin assistant.',
    recommendedSkills: ['calendar_management', 'itinerary_builder'],
    recommendedTools: ['google_calendar', 'weather_api'],
    reasoningEffort: 'low',
    typicalTasks: ['Weekly schedule deconfliction', 'Flight reservation comparison'],
  },
  {
    roleId: 'office_manager',
    category: 'office_manager',
    displayName: 'Office Manager Bot',
    description: 'Internal workplace operations coordinator managing meeting rooms and supply replenishment.',
    personaPrompt: 'You are a diligent, diplomatic Office Operations Manager.',
    recommendedSkills: ['facility_booking', 'expense_claim_auditor'],
    recommendedTools: ['slack_webhook', 'confluence_api'],
    reasoningEffort: 'medium',
    typicalTasks: ['Meeting room dispute resolution', 'Hardware requisition auditing'],
  },
  {
    roleId: 'clipper',
    category: 'clipper',
    displayName: 'Knowledge Clipper & Distiller',
    description: 'Deep researcher specialized in extracting, synthesizing, and archiving high-value insights.',
    personaPrompt: 'You are a sharp, analytical Knowledge Clipper.',
    recommendedSkills: ['web_scraping', 'executive_summary'],
    recommendedTools: ['tavily_search', 'browser_snapshot'],
    reasoningEffort: 'high',
    typicalTasks: ['Competitor technical teardown distillation', 'Daily newsletter synthesis'],
  },
  {
    roleId: 'chief_of_staff',
    category: 'chief_of_staff',
    displayName: 'Chief of Staff Orchestrator',
    description: 'Executive task delegator orchestrating cross-agent workflows, risk mitigation, and priorities.',
    personaPrompt: 'You are a decisive, strategic Chief of Staff.',
    recommendedSkills: ['task_decomposition', 'priority_arbitration'],
    recommendedTools: ['workflow_dag_runner', 'fusen_board_sync'],
    reasoningEffort: 'high',
    typicalTasks: ['Quarterly OKR breakdown into bot trees', 'Cross-functional blocker triage'],
  },
  {
    roleId: 'sales_team',
    category: 'sales_team',
    displayName: 'B2B Sales Development Rep',
    description: 'Lead qualification, inbound inquiry enrichment, CRM record updating, and personalized outreach.',
    personaPrompt: 'You are a persuasive, detail-oriented Sales Development Representative.',
    recommendedSkills: ['lead_scoring', 'cold_email_drafting'],
    recommendedTools: ['hubspot_crm', 'linkedin_enrichment'],
    reasoningEffort: 'medium',
    typicalTasks: ['Inbound lead qualification against ICP', 'Personalized outreach email generation'],
  },
];
