/**
 * Git Worktree and Session Checkout Anchoring Domain Types.
 *
 * [INPUT] None (Standard TypeScript)
 * [OUTPUT] Pure types for worktree management, session checkout anchors, and touched files.
 * [POS] src/components/features/git-worktree/worktreeTypes.ts
 */

export interface GitWorktree {
  path: string;
  branch: string;
  head_commit: string;
  is_current: boolean;
  is_bare: boolean;
  is_dirty: boolean;
  is_locked: boolean;
  lock_reason: string | null;
}

export interface CreateWorktreeDTO {
  branch: string;
  repo_path?: string;
  worktree_path?: string;
  base_ref?: string;
}

export interface SessionTouchedFile {
  file_path: string;
  change_type: 'created' | 'modified' | 'deleted' | 'read';
  touched_at: string;
}

export interface SessionCheckoutAnchor {
  session_id: string;
  project_root: string;
  worktree_path: string;
  checkout_ref: string;
  is_anchored: boolean;
  active_worktree_path: string;
  touched_files: SessionTouchedFile[];
  created_at: string;
}

/** Stable failure codes of `POST /git/worktrees`; the UI owns the wording for each. */
export type WorktreeFailureReason =
  | 'unsafe-repository'
  | 'branch-exists'
  | 'already-checked-out'
  | 'path-exists'
  | 'not-git-repo'
  | 'error';

export interface WorktreeStoreState {
  worktrees: GitWorktree[];
  activeWorktree: GitWorktree | null;
  loading: boolean;
  error: string | null;
  /** Set when `error` came from a failed create, so the UI can show localized wording instead of `error`. */
  errorReason: WorktreeFailureReason | null;
  currentSessionAnchor: SessionCheckoutAnchor | null;
  createModalOpen: boolean;
}

export interface WorktreeStoreActions {
  fetchWorktrees: (repoPath?: string) => Promise<void>;
  switchActiveWorktree: (worktreePath: string, repoPath?: string) => Promise<void>;
  createNewWorktree: (dto: CreateWorktreeDTO) => Promise<GitWorktree>;
  checkSessionAnchor: (sessionId: string, repoPath?: string) => Promise<SessionCheckoutAnchor>;
  syncSessionToAnchor: (sessionId: string) => Promise<void>;
  setCreateModalOpen: (open: boolean) => void;
  resetError: () => void;
}

export type WorktreeStore = WorktreeStoreState & WorktreeStoreActions;
