/**
 * Error raised when the server refuses or cannot complete a worktree request.
 *
 * [INPUT] ./worktreeTypes
 * [OUTPUT] WorktreeRequestError: Carries the server's stable failure code so the UI can show its own localized wording.
 * [POS] src/components/features/git-worktree/worktreeErrors.ts
 */

import type { WorktreeFailureReason } from './worktreeTypes';

export class WorktreeRequestError extends Error {
  constructor(
    public readonly reason: WorktreeFailureReason,
    message: string,
  ) {
    super(message);
    this.name = 'WorktreeRequestError';
  }
}
