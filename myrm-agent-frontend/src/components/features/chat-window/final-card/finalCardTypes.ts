/**
 * [INPUT]
 * - None (Pure domain type definitions for Terminal-Free Final Card Presentation Contract)
 *
 * [OUTPUT]
 * - FinalCardStatus, FinalCardActionOption, FinalCardArtifact,
 *   FinalCardPresentationContract, FinalCardStoreState
 *
 * [POS]
 * Unified presentation contract for Item 192 (P0): TerminalFreeFinalCardPresentationContractSuite.
 * Eradicates token-by-token terminal surveillance by decoupling final presentation cards
 * from raw execution logs, exposing structured decisions, next-action options, and transcript links.
 */

export type FinalCardStatus =
  | 'completed'
  | 'requires_action'
  | 'failed'
  | 'partial_success';

export interface FinalCardActionOption {
  readonly id: string;
  readonly label: string;
  readonly actionKind: 'run_tests' | 'review_diff' | 'commit_code' | 'deep_dive' | 'custom';
  readonly payload?: string;
  readonly isPrimary?: boolean;
}

export interface FinalCardArtifact {
  readonly id: string;
  readonly name: string;
  readonly type: 'code' | 'document' | 'diff' | 'binary';
  readonly path: string;
  readonly sizeBytes?: number;
  readonly previewable: boolean;
}

export interface FinalCardPresentationContract {
  readonly id: string;
  readonly turnId: string;
  readonly status: FinalCardStatus;
  readonly title: string;
  readonly summary: string;
  readonly keyDecisions: readonly string[];
  readonly artifacts: readonly FinalCardArtifact[];
  readonly actionOptions: readonly FinalCardActionOption[];
  readonly executionDurationMs: number;
  readonly tokensUsed?: {
    readonly prompt: number;
    readonly completion: number;
    readonly total: number;
  };
  readonly transcriptUrl: string;
  readonly rawLogLinesCount: number;
  readonly rawLogsPreview?: readonly string[];
  readonly timestamp: number;
}

export interface FinalCardStoreState {
  readonly cards: Readonly<Record<string, FinalCardPresentationContract>>;
  readonly activeTranscriptCardId: string | null;
}
