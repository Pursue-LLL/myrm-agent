/**
 * Debounced whole-workspace file-name search for the workbench Files tab
 *
 * [INPUT]
 * - @/services/chat::searchWorkspaceFiles (POS: server-side fuzzy file-name search, silent on failure)
 *
 * [OUTPUT]
 * - useWorkspaceFileSearch: The search state of one workspace and query
 *
 * [POS]
 * The loaded file tree only reaches a few levels deep, so a name typed into the Files tab is looked up on the
 * server, which walks the whole workspace. Only the newest query may report: a slower answer to an earlier
 * query or another workspace is dropped.
 */

import { useEffect, useState } from 'react';
import { searchWorkspaceFiles, type WorkspaceFileSearchResult } from '@/services/chat';

const DEBOUNCE_MS = 250;

export type WorkspaceFileSearchStatus = 'idle' | 'searching' | 'done' | 'failed';

export interface WorkspaceFileSearchState {
  status: WorkspaceFileSearchStatus;
  /** Matches of the newest finished search; while a newer one runs they are the previous matches. */
  results: WorkspaceFileSearchResult[];
}

interface FinishedSearch {
  workspace: string;
  key: string;
  status: 'done' | 'failed';
  results: WorkspaceFileSearchResult[];
}

const IDLE: WorkspaceFileSearchState = { status: 'idle', results: [] };

export function useWorkspaceFileSearch(workspace: string | null, query: string): WorkspaceFileSearchState {
  const [finished, setFinished] = useState<FinishedSearch | null>(null);
  const needle = query.trim();
  const key = workspace && needle ? `${workspace}\n${needle}` : null;

  useEffect(() => {
    if (!workspace || !key) {
      return;
    }
    let superseded = false;
    const timer = setTimeout(() => {
      searchWorkspaceFiles(workspace, needle)
        .then(({ results }) => {
          if (!superseded) {
            setFinished({ workspace, key, status: 'done', results });
          }
        })
        .catch(() => {
          if (!superseded) {
            setFinished({ workspace, key, status: 'failed', results: [] });
          }
        });
    }, DEBOUNCE_MS);
    return () => {
      superseded = true;
      clearTimeout(timer);
    };
  }, [workspace, needle, key]);

  if (!key) {
    return IDLE;
  }
  if (finished?.key === key) {
    return { status: finished.status, results: finished.results };
  }
  return { status: 'searching', results: finished?.workspace === workspace ? finished.results : [] };
}
