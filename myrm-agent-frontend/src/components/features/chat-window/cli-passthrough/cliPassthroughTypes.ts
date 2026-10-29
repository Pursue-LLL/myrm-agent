/**
 * [INPUT]
 * - None (Pure domain type definitions for Direct CLI Pass-Through with Context Visibility Switch)
 *
 * [OUTPUT]
 * - CliPassThroughMode, CliExecutionStatus, CliCommandRecord,
 *   CliGuardAuditResult, CliPassthroughStoreState
 *
 * [POS]
 * Unified types for Item 194 (P0): DirectCliPassThroughWithContextVisibilitySwitchSuite.
 * Distinguishes '!cmd' (injected into context for LLM reasoning) from '!!cmd'
 * (user inspection only, 0 token waste, strictly excluded from context).
 */

export type CliPassThroughMode =
  | 'visible_to_context'    // !cmd: Output appended to chat context for Agent awareness
  | 'user_inspection_only'; // !!cmd: Output stays in local drawer, 0 token overhead

export type CliExecutionStatus =
  | 'idle'
  | 'running'
  | 'success'
  | 'failed'
  | 'blocked_by_guard';

export interface CliCommandRecord {
  readonly id: string;
  readonly rawInput: string;
  readonly command: string;
  readonly mode: CliPassThroughMode;
  readonly status: CliExecutionStatus;
  readonly output: string;
  readonly exitCode: number | null;
  readonly durationMs: number;
  readonly timestamp: number;
  readonly guardReason?: string;
}

export interface CliGuardAuditResult {
  readonly allowed: boolean;
  readonly reason?: string;
}

export interface CliPassthroughStoreState {
  readonly history: readonly CliCommandRecord[];
  readonly activeCommand: CliCommandRecord | null;
  readonly isDrawerOpen: boolean;
  readonly isExecuting: boolean;
}
