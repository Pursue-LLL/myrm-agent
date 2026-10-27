/**
 * [INPUT]
 * - @/lib/api::ApiError (POS: carries the backend `ErrorDetail[]` of a rejected request)
 *
 * [OUTPUT]
 * - workspacePathIssueMessageKey: which `common.workspacePathIssue.*` message explains a refused workspace folder
 *
 * [POS]
 * Folder pickers and the project folder dialogs share one reading of the backend's workspace refusal,
 * so every entry that binds a workspace words it the same way.
 */

import { ApiError } from '@/lib/api';

export type WorkspacePathIssueMessageKey = 'tooBroad' | 'dangerous';

/** Backend `ErrorDetail.field` values that name a workspace folder. */
const WORKSPACE_FIELDS: ReadonlySet<string> = new Set(['workspace_dir', 'workspace_path']);

/** Backend `ErrorDetail.issue` values that have a dedicated message; any other refusal keeps the caller's generic one. */
const MESSAGE_KEY_BY_ISSUE: ReadonlyMap<string, WorkspacePathIssueMessageKey> = new Map([
  ['too_broad', 'tooBroad'],
  ['dangerous', 'dangerous'],
]);

export function workspacePathIssueMessageKey(error: unknown): WorkspacePathIssueMessageKey | null {
  if (!(error instanceof ApiError)) {
    return null;
  }
  for (const detail of error.details) {
    if (detail.field && WORKSPACE_FIELDS.has(detail.field)) {
      const key = MESSAGE_KEY_BY_ISSUE.get(detail.issue);
      if (key) {
        return key;
      }
    }
  }
  return null;
}
