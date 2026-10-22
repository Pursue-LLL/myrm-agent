/**
 * [INPUT]: Multi-source evidence telemetry, 4-tier confidence scores, and action-oriented findings.
 * [OUTPUT]: Strong TypeScript definitions for EvidenceCrossVerificationCockpit component.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/evidenceCrossVerificationTypes.ts
 */

export type EvidenceSourceTypeEnum =
  | 'KNOWLEDGE_BASE'
  | 'CODE_SYMBOL'
  | 'SOURCE_LOGIC'
  | 'RUNTIME_TELEMETRY';

export type ConfidenceLevelEnum = 'HIGH' | 'MEDIUM' | 'LOW';

export interface EvidenceItemData {
  source_type: EvidenceSourceTypeEnum;
  title: string;
  detail: string;
  is_verified: boolean;
  timestamp_ms: number;
  weight: number;
  file_path: string;
  line_number: number;
  trace_id: string;
}

export interface VerificationFindingData {
  diagnosis_id: string;
  error_code: string;
  resolved_code_meaning: string;
  target_file_path: string;
  target_line_number: number;
  root_cause_category: string;
  explanation: string;
  recommended_patch: string;
  confidence_score: number;
  confidence_level: ConfidenceLevelEnum;
  evidences: EvidenceItemData[];
  bilateral_verified: boolean;
  created_at_ms: number;
}

export interface EvidenceCrossVerificationCockpitProps {
  activeFinding?: VerificationFindingData | null;
  recentDiagnoses?: VerificationFindingData[];
  onDiagnose?: (errorCode: string) => Promise<void> | void;
  onReset?: () => Promise<void> | void;
  isDiagnosing?: boolean;
}
