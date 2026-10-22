/**
 * Zustand Store for Git Worktree Management and Session Checkout Anchoring.
 *
 * [INPUT] zustand, ./worktreeTypes, ./worktreeService
 * [OUTPUT] useWorktreeStore: Hook for state and actions across sidebar and session views.
 * [POS] src/components/features/git-worktree/useWorktreeStore.ts
 */

import { create } from 'zustand';
import type { CreateWorktreeDTO, GitWorktree, SessionCheckoutAnchor, WorktreeStore } from './worktreeTypes';
import { worktreeService } from './worktreeService';

export const useWorktreeStore = create<WorktreeStore>((set, get) => ({
  worktrees: [],
  activeWorktree: null,
  loading: false,
  error: null,
  currentSessionAnchor: null,
  createModalOpen: false,

  fetchWorktrees: async (repoPath?: string) => {
    set({ loading: true, error: null });
    try {
      const list = await worktreeService.listWorktrees(repoPath);
      const active = list.find((w) => w.is_current) || list[0] || null;
      set({ worktrees: list, activeWorktree: active, loading: false });
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch worktrees';
      set({ error: msg, loading: false });
    }
  },

  switchActiveWorktree: async (worktreePath: string, repoPath?: string) => {
    set({ loading: true, error: null });
    try {
      const switched = await worktreeService.switchWorktree(worktreePath, repoPath);
      const list = get().worktrees.map((w) => ({
        ...w,
        is_current: w.path === switched.path,
      }));
      const anchor = get().currentSessionAnchor;
      const updatedAnchor = anchor
        ? {
            ...anchor,
            active_worktree_path: switched.path,
            is_anchored: anchor.worktree_path === switched.path,
          }
        : null;

      set({
        worktrees: list,
        activeWorktree: switched,
        currentSessionAnchor: updatedAnchor,
        loading: false,
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to switch worktree';
      set({ error: msg, loading: false });
    }
  },

  createNewWorktree: async (dto: CreateWorktreeDTO): Promise<GitWorktree> => {
    set({ loading: true, error: null });
    try {
      const created = await worktreeService.createWorktree(dto);
      const list = [...get().worktrees.filter((w) => w.path !== created.path), created].map((w) => ({
        ...w,
        is_current: w.path === created.path,
      }));
      set({
        worktrees: list,
        activeWorktree: created,
        createModalOpen: false,
        loading: false,
      });
      return created;
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to create worktree';
      set({ error: msg, loading: false });
      throw err;
    }
  },

  removeWorktree: async (worktreePath: string, force = false) => {
    set({ loading: true, error: null });
    try {
      await worktreeService.removeWorktree(worktreePath, force);
      const list = get().worktrees.filter((w) => w.path !== worktreePath);
      let active = get().activeWorktree;
      if (active?.path === worktreePath) {
        active = list[0] || null;
      }
      set({ worktrees: list, activeWorktree: active, loading: false });
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to remove worktree';
      set({ error: msg, loading: false });
    }
  },

  checkSessionAnchor: async (sessionId: string, repoPath?: string): Promise<SessionCheckoutAnchor> => {
    try {
      const anchor = await worktreeService.getSessionCheckoutAnchor(sessionId, repoPath);
      const active = get().activeWorktree;
      if (active) {
        anchor.active_worktree_path = active.path;
        anchor.is_anchored = anchor.worktree_path === active.path;
      }
      set({ currentSessionAnchor: anchor });
      return anchor;
    } catch {
      const fallback: SessionCheckoutAnchor = {
        session_id: sessionId,
        project_root: '/workspace',
        worktree_path: get().activeWorktree?.path || '/workspace',
        checkout_ref: get().activeWorktree?.branch || 'main',
        is_anchored: true,
        active_worktree_path: get().activeWorktree?.path || '/workspace',
        touched_files: [],
        created_at: new Date().toISOString(),
      };
      set({ currentSessionAnchor: fallback });
      return fallback;
    }
  },

  syncSessionToAnchor: async (sessionId: string) => {
    const anchor = get().currentSessionAnchor;
    if (!anchor || anchor.session_id !== sessionId) {
      const fetched = await get().checkSessionAnchor(sessionId);
      if (fetched.worktree_path) {
        await get().switchActiveWorktree(fetched.worktree_path);
      }
      return;
    }

    if (anchor.worktree_path) {
      await get().switchActiveWorktree(anchor.worktree_path);
    }
  },

  setCreateModalOpen: (open: boolean) => {
    set({ createModalOpen: open });
  },

  resetError: () => {
    set({ error: null });
  },
}));
