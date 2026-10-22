'use client';

/**
 * Git Worktree Dropdown Switcher for Sidebar.
 *
 * [INPUT] useWorktreeStore, lucide-react, next-intl
 * [OUTPUT] GitWorktreeDropdown: Compact sidebar dropdown for listing, switching, and creating worktrees.
 * [POS] src/components/features/git-worktree/GitWorktreeDropdown.tsx
 */

import { memo, useState, useEffect, useRef, useCallback } from 'react';
import {
  GitBranch,
  ChevronDown,
  Check,
  Plus,
  AlertCircle,
  FolderGit2,
  X,
  Loader2,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { useWorktreeStore } from './useWorktreeStore';

export interface GitWorktreeDropdownProps {
  className?: string;
  repoPath?: string;
}

export const GitWorktreeDropdown = memo(function GitWorktreeDropdown({
  className,
  repoPath,
}: GitWorktreeDropdownProps) {
  const t = useTranslations('gitWorktree');
  const {
    worktrees,
    activeWorktree,
    loading,
    error,
    createModalOpen,
    fetchWorktrees,
    switchActiveWorktree,
    createNewWorktree,
    setCreateModalOpen,
    resetError,
  } = useWorktreeStore();

  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [newBranchName, setNewBranchName] = useState('');
  const [baseRef, setBaseRef] = useState('HEAD');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    fetchWorktrees(repoPath);
  }, [fetchWorktrees, repoPath]);

  // Click outside listener for dropdown
  useEffect(() => {
    if (!dropdownOpen) {
      return;
    }
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [dropdownOpen]);

  // Sync dialog visibility with state
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) {
      return;
    }
    if (createModalOpen && !dialog.open) {
      dialog.showModal();
    } else if (!createModalOpen && dialog.open) {
      dialog.close();
    }
  }, [createModalOpen]);

  const handleSelectWorktree = useCallback(
    async (path: string) => {
      setDropdownOpen(false);
      if (activeWorktree?.path === path) {
        return;
      }
      await switchActiveWorktree(path, repoPath);
    },
    [activeWorktree, switchActiveWorktree, repoPath],
  );

  const handleCreateSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      const branch = newBranchName.trim();
      if (!branch) {
        return;
      }

      setIsSubmitting(true);
      try {
        await createNewWorktree({
          branch,
          base_ref: baseRef || 'HEAD',
          repo_path: repoPath,
        });
        setNewBranchName('');
        setBaseRef('HEAD');
        setCreateModalOpen(false);
      } catch {
        // error stored in store
      } finally {
        setIsSubmitting(false);
      }
    },
    [newBranchName, baseRef, createNewWorktree, repoPath, setCreateModalOpen],
  );

  return (
    <div
      ref={dropdownRef}
      className={cn('relative w-full text-xs font-medium', className)}
      data-testid="git-worktree-dropdown"
    >
      {/* Main Switcher Trigger */}
      <button
        type="button"
        onClick={() => {
          setDropdownOpen((prev) => !prev);
        }}
        disabled={loading && worktrees.length === 0}
        aria-haspopup="listbox"
        aria-expanded={dropdownOpen}
        className={cn(
          'w-full flex items-center justify-between gap-1.5 px-2.5 py-1.5 rounded-lg border transition-all text-left',
          'bg-muted/40 hover:bg-muted/70 border-border/50 text-foreground',
          'focus:outline-none focus:ring-1 focus:ring-primary/40',
        )}
      >
        <div className="flex items-center gap-1.5 min-w-0">
          <FolderGit2 className="h-3.5 w-3.5 flex-shrink-0 text-primary" />
          <span className="truncate max-w-[110px] font-semibold text-foreground">
            {activeWorktree?.branch || 'main'}
          </span>
          {activeWorktree?.head_commit && (
            <span className="text-[10px] text-muted-foreground font-mono bg-muted px-1 py-0.2 rounded flex-shrink-0">
              {activeWorktree.head_commit.slice(0, 7)}
            </span>
          )}
          {activeWorktree?.is_dirty && (
            <span
              className="h-1.5 w-1.5 rounded-full bg-amber-500 flex-shrink-0"
              title={t('dirtyChanges') || 'Uncommitted changes'}
            />
          )}
        </div>
        <ChevronDown
          className={cn(
            'h-3.5 w-3.5 text-muted-foreground transition-transform duration-200 flex-shrink-0',
            dropdownOpen && 'rotate-180',
          )}
        />
      </button>

      {/* Popover Menu */}
      {dropdownOpen && (
        <div
          data-testid="git-worktree-popover"
          className={cn(
            'absolute top-full left-0 right-0 mt-1 z-50 rounded-lg border border-border/80',
            'bg-popover text-popover-foreground shadow-lg backdrop-blur-md overflow-hidden',
            'animate-in fade-in-0 zoom-in-95 duration-100',
          )}
        >
          <div className="px-2.5 py-1.5 border-b border-border/40 text-[10px] text-muted-foreground uppercase tracking-wider flex items-center justify-between">
            <span>{t('worktrees') || 'Worktrees'}</span>
            <span className="font-mono text-[9px]">{worktrees.length}</span>
          </div>

          <div className="max-h-52 overflow-y-auto py-1">
            {worktrees.map((wt) => {
              const isSelected = activeWorktree?.path === wt.path;
              return (
                <button
                  key={wt.path}
                  type="button"
                  data-testid={`worktree-option-${wt.branch}`}
                  aria-pressed={isSelected}
                  onClick={() => {
                    handleSelectWorktree(wt.path);
                  }}
                  className={cn(
                    'w-full flex items-center justify-between px-2.5 py-1.5 text-left transition-colors',
                    'hover:bg-muted/60 focus:bg-muted/80 focus:outline-none',
                    isSelected && 'bg-primary/10 text-primary font-semibold',
                  )}
                >
                  <div className="flex items-center gap-1.5 min-w-0">
                    <GitBranch className="h-3 w-3 flex-shrink-0 text-muted-foreground" />
                    <span className="truncate max-w-[120px]">{wt.branch}</span>
                    {wt.is_dirty && (
                      <span className="text-[9px] text-amber-500 bg-amber-500/10 px-1 py-0.2 rounded">
                        dirty
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <span className="text-[10px] font-mono text-muted-foreground">
                      {wt.head_commit.slice(0, 6)}
                    </span>
                    {isSelected && <Check className="h-3.5 w-3.5 text-primary" />}
                  </div>
                </button>
              );
            })}
          </div>

          {/* Create Action Row */}
          <div className="border-t border-border/40 p-1">
            <button
              type="button"
              onClick={() => {
                setDropdownOpen(false);
                setCreateModalOpen(true);
              }}
              className={cn(
                'w-full flex items-center justify-center gap-1 px-2 py-1.5 rounded text-xs',
                'text-primary hover:bg-primary/10 transition-colors font-medium',
              )}
            >
              <Plus className="h-3.5 w-3.5" />
              <span>{t('newWorktree') || 'New Worktree'}</span>
            </button>
          </div>
        </div>
      )}

      {/* Native <dialog> Modal for Creating Worktree */}
      <dialog
        ref={dialogRef}
        aria-modal="true"
        aria-labelledby="worktree-create-modal-title"
        className={cn(
          'p-0 rounded-xl bg-background border border-border shadow-2xl backdrop:bg-black/50 backdrop:backdrop-blur-sm',
          'w-full max-w-sm m-auto text-foreground',
        )}
      >
        <div className="p-4 flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <h3 id="worktree-create-modal-title" className="text-sm font-semibold flex items-center gap-1.5">
              <FolderGit2 className="h-4 w-4 text-primary" />
              <span>{t('createTitle') || 'Create New Worktree'}</span>
            </h3>
            <button
              type="button"
              onClick={() => {
                setCreateModalOpen(false);
              }}
              className="text-muted-foreground hover:text-foreground p-1 rounded-md"
              aria-label={t('close') || 'Close'}
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {error && (
            <div className="p-2 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-[11px] flex items-center gap-1.5">
              <AlertCircle className="h-3.5 w-3.5 flex-shrink-0" />
              <span className="truncate">{error}</span>
              <button
                type="button"
                onClick={resetError}
                className="ml-auto text-xs underline"
              >
                {t('dismiss') || 'Dismiss'}
              </button>
            </div>
          )}

          <form onSubmit={handleCreateSubmit} className="flex flex-col gap-3">
            <div>
              <label htmlFor="wt-branch-input" className="block text-[11px] text-muted-foreground mb-1 font-medium">
                {t('branchName') || 'Branch Name'}
              </label>
              <input
                id="wt-branch-input"
                type="text"
                required
                placeholder="e.g. feature/auth-refactor"
                value={newBranchName}
                onChange={(e) => {
                  setNewBranchName(e.target.value);
                }}
                className={cn(
                  'w-full px-2.5 py-1.5 rounded-lg border border-border bg-muted/40 text-xs',
                  'focus:outline-none focus:ring-1 focus:ring-primary',
                )}
              />
            </div>

            <div>
              <label htmlFor="wt-base-ref-input" className="block text-[11px] text-muted-foreground mb-1 font-medium">
                {t('baseRef') || 'Base Ref (Branch or Commit)'}
              </label>
              <input
                id="wt-base-ref-input"
                type="text"
                placeholder="HEAD"
                value={baseRef}
                onChange={(e) => {
                  setBaseRef(e.target.value);
                }}
                className={cn(
                  'w-full px-2.5 py-1.5 rounded-lg border border-border bg-muted/40 text-xs font-mono',
                  'focus:outline-none focus:ring-1 focus:ring-primary',
                )}
              />
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-border/40">
              <button
                type="button"
                onClick={() => {
                  setCreateModalOpen(false);
                }}
                className="px-3 py-1.5 text-xs rounded-lg hover:bg-muted text-muted-foreground"
              >
                {t('cancel') || 'Cancel'}
              </button>
              <button
                type="submit"
                disabled={isSubmitting || !newBranchName.trim()}
                className={cn(
                  'px-3 py-1.5 text-xs rounded-lg bg-primary text-primary-foreground font-semibold flex items-center gap-1.5',
                  'hover:opacity-90 disabled:opacity-50 transition-opacity',
                )}
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="h-3 w-3 animate-spin" />
                    <span>{t('creating') || 'Creating...'}</span>
                  </>
                ) : (
                  <span>{t('confirm') || 'Create Worktree'}</span>
                )}
              </button>
            </div>
          </form>
        </div>
      </dialog>
    </div>
  );
});
