export type ExitCauseCategory =
  | 'oom_killed'
  | 'missing_dependency'
  | 'port_conflict'
  | 'auth_invalid'
  | 'network_timeout'
  | 'permission_denied'
  | 'unknown_failure';

export interface ActionableFixGuide {
  actionId: string;
  buttonLabel: string;
  actionType: 'auto_install' | 'open_settings' | 'change_port' | 'increase_memory' | 'retry_command';
  payload?: Record<string, string>;
  isRecommended: boolean;
}

export interface ClassifiedDiagnosticResult {
  category: ExitCauseCategory;
  categoryLabel: string;
  exitCode: number;
  rootCauseSummary: string;
  sanitizedStderrSnippet: string;
  confidenceScore: number;
  fixGuides: ActionableFixGuide[];
  occurredAt: string;
}

export interface StderrDiagnosticState {
  rawBuffer: string;
  maxBufferBytes: number;
  activeDiagnostic: ClassifiedDiagnosticResult | null;
  isFixing: boolean;
  fixSuccessMessage: string | null;

  ingestStderrChunk: (chunk: string) => void;
  classifyProcessExit: (exitCode: number) => ClassifiedDiagnosticResult;
  executeFixAction: (actionId: string) => Promise<void>;
  dismissDiagnostic: () => void;
  resetDiagnosticState: () => void;
}
