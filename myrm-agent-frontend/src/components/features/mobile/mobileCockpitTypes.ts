/**
 * [INPUT]
 * None - Pure TypeScript Contract definitions.
 *
 * [OUTPUT]
 * - HitlRiskLevel, HitlDecisionType, HitlApprovalPayload, HitlDecisionResult
 * - TouchOptionItem, TouchSelectionMode
 * - MobileVoiceStagedProps, MobileHitlApprovalProps, TouchFriendlySelectionProps
 *
 * [POS]
 * Type contracts for Mobile Remote Companion and Touch-Optimized HITL Cockpit.
 */

export type HitlRiskLevel = 'low' | 'medium' | 'high' | 'critical';

export type HitlDecisionType = 'approve' | 'reject' | 'steer';

export interface HitlApprovalPayload {
  requestId: string;
  actionTitle: string;
  commandOrTool: string;
  scopeDescription: string;
  riskLevel: HitlRiskLevel;
  rawParams?: Record<string, string | number | boolean>;
  timestamp?: string;
}

export interface HitlDecisionResult {
  requestId: string;
  decision: HitlDecisionType;
  reason?: string;
  steerInstruction?: string;
}

export interface TouchOptionItem {
  id: string;
  label: string;
  description?: string;
  badge?: string;
  shortcut?: string;
  disabled?: boolean;
}

export type TouchSelectionMode = 'single' | 'multiple';

export interface MobileVoiceStagedInputProps {
  isOpen: boolean;
  onClose: () => void;
  onSend: (text: string) => void;
  className?: string;
}

export interface MobileHitlApprovalCardProps {
  payload: HitlApprovalPayload;
  onDecision: (result: HitlDecisionResult) => Promise<void> | void;
  isProcessing?: boolean;
  className?: string;
}

export interface TouchFriendlySelectionListProps {
  options: TouchOptionItem[];
  mode?: TouchSelectionMode;
  selectedIds: string[];
  onChange: (selectedIds: string[]) => void;
  onConfirm?: (selectedIds: string[]) => void;
  title?: string;
  className?: string;
}

export interface MobileAgentActionBarProps {
  onOpenVoice: () => void;
  onOpenSkills: () => void;
  onStopAgent: () => void;
  onToggleSessions: () => void;
  isRunning?: boolean;
  isStopping?: boolean;
  className?: string;
}
