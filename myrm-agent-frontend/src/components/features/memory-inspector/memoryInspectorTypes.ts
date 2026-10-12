/**
 * Type contracts for Memory Inspector & Epistemic Veracity Badge Suite.
 *
 * [INPUT] None
 * [OUTPUT] EpistemicTier, EpistemicMemoryItem, MemoryGovernanceAction
 * [POS] Item 30 type contracts. Strictly under 120 lines. Zero `any`.
 */

export type EpistemicTier = 'assertion' | 'observation' | 'belief';

export interface EpistemicMemoryItem {
  id: string;
  content: string;
  epistemic_tier: EpistemicTier;
  confidence_score: number;
  similarity_score: number;
  source_session_id?: string | null;
  hit_count: number;
  created_at: string;
  last_recalled_at?: string | null;
  provenance_chain: string[];
}

export type MemoryGovernanceAction = 'promote' | 'correct' | 'forget';

export interface EpistemicBadgeProps {
  tier: EpistemicTier;
  confidenceScore?: number;
  compact?: boolean;
  className?: string;
}

export interface MemoryCitationBadgeProps {
  memories: EpistemicMemoryItem[];
  sessionId?: string;
  onClick?: () => void;
  className?: string;
}

export interface MemoryInspectorDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  memories: EpistemicMemoryItem[];
  sessionId: string;
  onPromote?: (memoryId: string, targetTier?: 'assertion' | 'observation') => Promise<void> | void;
  onCorrect?: (memoryId: string, newContent: string) => Promise<void> | void;
  onForget?: (memoryId: string) => Promise<void> | void;
  className?: string;
}
