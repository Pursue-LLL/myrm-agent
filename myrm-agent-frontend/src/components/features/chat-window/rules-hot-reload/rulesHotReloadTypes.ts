/**
 * [INPUT]
 * - None (Pure domain type definitions for Workspace Rules Hot-Reload & Event Bus)
 *
 * [OUTPUT]
 * - WorkspaceRuleFile, RulesReloadSource, RuleDiffType, RuleFileDiff,
 *   RulesReloadEventPayload, WorkspaceRulesStoreState
 *
 * [POS]
 * Unified contracts for Item 199 (P1): WorkspaceRulesHotReloadAndEventBusSuite.
 * Supports zero-restart AGENTS.md / CLAUDE.md file-watcher hot reload,
 * real-time session invalidation event bus, and global rules bypass switch (--no-context-files).
 */

export interface WorkspaceRuleFile {
  readonly path: string;
  readonly filename: string;
  readonly content: string;
  readonly hash: string;
  readonly lastModified: number;
  readonly sizeBytes: number;
}

export type RulesReloadSource = 'file_watcher' | 'manual_reload' | 'slash_command';

export type RuleDiffType = 'added' | 'modified' | 'removed';

export interface RuleFileDiff {
  readonly filename: string;
  readonly diffType: RuleDiffType;
  readonly previousHash?: string;
  readonly currentHash?: string;
}

export interface RulesReloadEventPayload {
  readonly source: RulesReloadSource;
  readonly diffs: readonly RuleFileDiff[];
  readonly combinedHash: string;
  readonly timestamp: number;
}

export interface WorkspaceRulesStoreState {
  readonly ruleFiles: readonly WorkspaceRuleFile[];
  readonly combinedHash: string;
  readonly bypassRules: boolean;
  readonly isReloading: boolean;
  readonly lastReloadedAt: number | null;
  readonly lastReloadSource: RulesReloadSource | null;
  readonly notificationMessage: string | null;
}
