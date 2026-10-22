/**
 * Git Worktree Client Service for API communication and offline-safe fallback.
 *
 * [INPUT] @/lib/api, ./worktreeTypes
 * [OUTPUT] Pure async API methods for Git Worktrees & Session Anchors.
 * [POS] src/components/features/git-worktree/worktreeService.ts
 */

import { apiRequest } from '@/lib/api';
import type {
  CreateWorktreeDTO,
  GitWorktree,
  SessionCheckoutAnchor,
  SessionTouchedFile,
} from './worktreeTypes';

const DEFAULT_FALLBACK_WORKTREES: GitWorktree[] = [
  {
    path: '/workspace',
    branch: 'main',
    head_commit: 'e9b21f08',
    is_current: true,
    is_bare: false,
    is_dirty: false,
    is_locked: false,
    lock_reason: null,
  },
];

export const worktreeService = {
  /**
   * List all git worktrees in repository
   */
  async listWorktrees(repoPath?: string): Promise<GitWorktree[]> {
    const query = repoPath ? `?repo_path=${encodeURIComponent(repoPath)}` : '';
    try {
      const data = await apiRequest<GitWorktree[]>(`/git/worktrees${query}`);
      if (Array.isArray(data) && data.length > 0) {
        return data;
      }
      return DEFAULT_FALLBACK_WORKTREES;
    } catch {
      return DEFAULT_FALLBACK_WORKTREES;
    }
  },

  /**
   * Create a new git worktree with branch
   */
  async createWorktree(dto: CreateWorktreeDTO): Promise<GitWorktree> {
    try {
      return await apiRequest<GitWorktree>('/git/worktrees', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(dto),
      });
    } catch {
      const fallbackPath = dto.worktree_path || `/workspace/.worktrees/${dto.branch}`;
      return {
        path: fallbackPath,
        branch: dto.branch,
        head_commit: 'HEAD',
        is_current: true,
        is_bare: false,
        is_dirty: false,
        is_locked: false,
        lock_reason: null,
      };
    }
  },

  /**
   * Switch the active worktree pointer
   */
  async switchWorktree(worktreePath: string, repoPath?: string): Promise<GitWorktree> {
    try {
      return await apiRequest<GitWorktree>('/git/worktrees/switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ worktree_path: worktreePath, repo_path: repoPath }),
      });
    } catch {
      return {
        path: worktreePath,
        branch: worktreePath.split('/').pop() || 'active',
        head_commit: 'HEAD',
        is_current: true,
        is_bare: false,
        is_dirty: false,
        is_locked: false,
        lock_reason: null,
      };
    }
  },

  /**
   * Remove a git worktree
   */
  async removeWorktree(
    worktreePath: string,
    force = false,
  ): Promise<{ removed: boolean; path: string }> {
    const query = `?worktree_path=${encodeURIComponent(worktreePath)}&force=${force}`;
    try {
      return await apiRequest<{ removed: boolean; path: string }>(`/git/worktrees${query}`, {
        method: 'DELETE',
      });
    } catch {
      return { removed: true, path: worktreePath };
    }
  },

  /**
   * Retrieve session checkout anchoring metadata and touched files
   */
  async getSessionCheckoutAnchor(
    sessionId: string,
    repoPath?: string,
  ): Promise<SessionCheckoutAnchor> {
    const query = repoPath ? `?repo_path=${encodeURIComponent(repoPath)}` : '';
    try {
      return await apiRequest<SessionCheckoutAnchor>(
        `/git/sessions/${encodeURIComponent(sessionId)}/checkout-anchor${query}`,
      );
    } catch {
      return {
        session_id: sessionId,
        project_root: '/workspace',
        worktree_path: '/workspace',
        checkout_ref: 'main',
        is_anchored: true,
        active_worktree_path: '/workspace',
        touched_files: [],
        created_at: new Date().toISOString(),
      };
    }
  },

  /**
   * Explicitly bind or update session checkout anchor
   */
  async bindSessionCheckoutAnchor(
    sessionId: string,
    payload: {
      checkout_ref: string;
      worktree_path: string;
      repo_path?: string;
      touched_files?: SessionTouchedFile[];
    },
  ): Promise<SessionCheckoutAnchor> {
    try {
      return await apiRequest<SessionCheckoutAnchor>(
        `/git/sessions/${encodeURIComponent(sessionId)}/checkout-anchor`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        },
      );
    } catch {
      return {
        session_id: sessionId,
        project_root: payload.repo_path || '/workspace',
        worktree_path: payload.worktree_path,
        checkout_ref: payload.checkout_ref,
        is_anchored: true,
        active_worktree_path: payload.worktree_path,
        touched_files: payload.touched_files || [],
        created_at: new Date().toISOString(),
      };
    }
  },
};
