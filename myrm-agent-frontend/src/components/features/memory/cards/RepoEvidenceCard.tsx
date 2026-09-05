'use client';

/**
 * [INPUT]
 * @/services/memory/commandCenter::MemoryRepoEvidenceResponse
 *
 * [OUTPUT]
 * RepoEvidenceCard: Compact, non-intrusive repository history evidence & git provenance card.
 *
 * [POS]
 * Command Center Workspace Memory tab. Renders recent commits and workspace repository branch status.
 */

import { memo, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { GitBranch, GitCommit, RefreshCw, FolderGit2, AlertCircle, FileCode } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import {
  getRepoEvidenceDigest,
  type MemoryRepoEvidenceResponse,
} from '@/services/memory/commandCenter';

interface RepoEvidenceCardProps {
  workspacePath?: string;
  className?: string;
}

export const RepoEvidenceCard = memo<RepoEvidenceCardProps>(({ workspacePath, className }) => {
  const t = useTranslations('memory.commandCenter.repoEvidence');
  const [data, setData] = useState<MemoryRepoEvidenceResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchDigest = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getRepoEvidenceDigest(workspacePath);
      setData(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load repo evidence');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchDigest();
  }, [workspacePath]);

  if (!data && !loading && !error) {
    return null;
  }

  return (
    <div
      className={cn(
        'rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white/70 dark:bg-zinc-900/70 backdrop-blur-md p-4 shadow-xs transition-all',
        className,
      )}
    >
      <div className="flex items-center justify-between pb-3 border-b border-zinc-100 dark:border-zinc-800/60">
        <div className="flex items-center gap-2">
          <span className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-600 dark:text-indigo-400">
            <FolderGit2 className="w-4 h-4" />
          </span>
          <div>
            <h4 className="text-xs font-semibold text-zinc-900 dark:text-zinc-100">
              {data?.repo_name || t('title')}
            </h4>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="inline-flex items-center gap-1 text-[11px] text-zinc-500 dark:text-zinc-400">
                <GitBranch className="w-3 h-3 text-indigo-400" />
                {data?.current_branch || 'none'}
              </span>
              {data?.is_dirty && (
                <span className="inline-flex items-center px-1.5 py-0.2 text-[10px] font-medium rounded-full bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 border border-amber-200/50 dark:border-amber-800/40">
                  {t('uncommittedChanges')}
                </span>
              )}
            </div>
          </div>
        </div>

        <button
          type="button"
          onClick={() => void fetchDigest()}
          disabled={loading}
          aria-label={t('refresh')}
          className="p-1.5 rounded-lg border border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors disabled:opacity-50"
        >
          <RefreshCw className={cn('w-3.5 h-3.5', loading && 'animate-spin')} />
        </button>
      </div>

      {error ? (
        <div className="py-4 flex items-center gap-2 text-xs text-rose-500 dark:text-rose-400">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      ) : (
        <div className="mt-3 space-y-2">
          <div className="text-[11px] font-medium text-zinc-400 dark:text-zinc-500">
            {t('recentCommits', { count: data?.recent_commits.length ?? 0 })}
          </div>

          {data?.recent_commits && data.recent_commits.length > 0 ? (
            <div className="space-y-1.5">
              {data.recent_commits.map((c) => (
                <div
                  key={c.commit_hash}
                  className="p-2 rounded-lg bg-zinc-50 dark:bg-zinc-800/40 border border-zinc-100 dark:border-zinc-800/60 text-xs flex flex-col gap-1"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium text-zinc-800 dark:text-zinc-200 truncate flex-1">
                      {c.subject}
                    </span>
                    <span className="inline-flex items-center gap-1 font-mono text-[10px] text-zinc-400 dark:text-zinc-500 shrink-0">
                      <GitCommit className="w-3 h-3 text-indigo-400" />
                      {c.short_hash}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-[10px] text-zinc-400 dark:text-zinc-500">
                    <span>{c.author}</span>
                    {c.files_changed.length > 0 && (
                      <span className="inline-flex items-center gap-0.5">
                        <FileCode className="w-2.5 h-2.5" />
                        {c.files_changed.length} {t('files')}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="py-3 text-center text-xs text-zinc-400 dark:text-zinc-500">
              {!data?.is_git_available ? t('gitUnavailable') : t('noCommits')}
            </div>
          )}
        </div>
      )}
    </div>
  );
});

RepoEvidenceCard.displayName = 'RepoEvidenceCard';
