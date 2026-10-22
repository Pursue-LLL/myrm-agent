/**
 * dualTrackTypes.ts
 * 业务极简模式 vs 深度工程模式双轨视图切换器与非程序员无感交互套件类型定义
 */

export type DualTrackViewMode = 'business' | 'engineering';

export type TurnMessageKind =
  | 'user_prompt'
  | 'clarification_qa'
  | 'business_plan'
  | 'business_summary'
  | 'artifact_preview'
  | 'tool_call'
  | 'terminal_output'
  | 'code_diff';

export interface ToolCallItem {
  id: string;
  toolName: string;
  inputSummary: string;
  outputPreview?: string;
  durationMs?: number;
  isError?: boolean;
}

export interface CodeDiffItem {
  filePath: string;
  diffText: string;
  additions: number;
  deletions: number;
  isNewFile?: boolean;
}

export interface TestAssertionItem {
  id: string;
  testName: string;
  passed: boolean;
  message?: string;
}

export interface EngineeringTraceDetails {
  turnId: string;
  toolCalls: ToolCallItem[];
  codeDiffs: CodeDiffItem[];
  terminalLogs: string[];
  testAssertions: TestAssertionItem[];
  timestamp: number;
}

export interface BusinessCardData {
  title: string;
  summary: string;
  planSteps?: string[];
  artifactId?: string;
}

export interface TurnMessageItem {
  id: string;
  role: 'user' | 'assistant' | 'system';
  kind: TurnMessageKind;
  content: string;
  businessCardData?: BusinessCardData;
  traceDetails?: EngineeringTraceDetails;
  timestamp: number;
}

export interface EngineeringTraceSummary {
  toolCount: number;
  diffCount: number;
  logLineCount: number;
  totalAdditions: number;
  totalDeletions: number;
  allTestsPassed: boolean;
}
