/**
 * Workspace text editing client: versioned read, save against the version that was read, save as copy.
 *
 * [INPUT]
 * - @/lib/api::apiRequest, ApiError (POS: authenticated REST client; `silent` hands failures to the caller)
 *
 * [OUTPUT]
 * - readWorkspaceText: file text plus the version token and whether the editor may change it
 * - saveWorkspaceText: save that the server refuses (`version_conflict`) when the file changed since it was read
 * - saveWorkspaceTextCopy: write the edited text to a new file next to the original
 * - WorkspaceTextError: a refusal the server named, with `reason` (and `currentVersion` for a conflict)
 * - encodeUtf8Base64: how text travels, so request-text sanitising can never rewrite file content
 *
 * [POS]
 * The only way the UI reads a file for editing or writes one back. There is no unconditional write: overwriting
 * after a conflict is a save against the current version the conflict response carries. Every call is `silent`;
 * the editor words each outcome itself and never shows the server's message.
 */

import { ApiError, apiRequest } from '@/lib/api';

const READONLY_REASONS = ['binary', 'not_utf8', 'mixed_line_endings', 'too_large'] as const;
const FAILURE_REASONS = [
  ...READONLY_REASONS,
  'version_conflict',
  'write_blocked',
  'not_found',
  'not_a_file',
  'invalid_content',
  'content_too_large',
  'name_unavailable',
] as const;

/** Why the editor cannot change a file. The file is still shown, except for `binary`, which has no text to show. */
export type WorkspaceTextReadonlyReason = (typeof READONLY_REASONS)[number];

/** Why the server refused a save or a copy. */
export type WorkspaceTextFailureReason = (typeof FAILURE_REASONS)[number];

function isFailureReason(value: string | undefined): value is WorkspaceTextFailureReason {
  return FAILURE_REASONS.some((reason) => reason === value);
}

export interface WorkspaceTextSnapshot {
  path: string;
  name: string;
  /** Line breaks are always `\n` here, whatever the file uses on disk. */
  content: string;
  /** Empty when the file is too large to be versioned. */
  version: string;
  /** Bytes on disk. */
  size: number;
  editable: boolean;
  readonlyReason: WorkspaceTextReadonlyReason | null;
  /** Only the beginning of the file is in `content`. */
  truncated: boolean;
}

export interface WorkspaceTextWritten {
  path: string;
  name: string;
  version: string;
  size: number;
  /** False when the saved text was already what the file held, so nothing was written. */
  changed: boolean;
}

interface SnapshotPayload {
  path: string;
  name: string;
  content: string;
  version: string;
  size: number;
  editable: boolean;
  readonly_reason: WorkspaceTextReadonlyReason | null;
  truncated: boolean;
}

/** A refusal the server named; anything it did not name is rethrown as it came. */
export class WorkspaceTextError extends Error {
  constructor(
    readonly reason: WorkspaceTextFailureReason,
    /** For `version_conflict`: the version the file has now, to save against when the user chooses to overwrite. */
    readonly currentVersion: string | null = null,
  ) {
    super(`Workspace text request refused: ${reason}`);
    this.name = 'WorkspaceTextError';
  }
}

const BASE64_CHUNK_BYTES = 0x8000;

/** UTF-8 then base64; chunked because spreading a megabyte of bytes into one call overflows the argument limit. */
export function encodeUtf8Base64(text: string): string {
  const bytes = new TextEncoder().encode(text);
  let binary = '';
  for (let offset = 0; offset < bytes.length; offset += BASE64_CHUNK_BYTES) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + BASE64_CHUNK_BYTES));
  }
  return btoa(binary);
}

function detailIssue(error: ApiError, field: string): string | undefined {
  return error.details.find((detail) => detail.field === field)?.issue;
}

function asWorkspaceTextError(error: unknown): unknown {
  if (!(error instanceof ApiError)) {
    return error;
  }
  const reason = detailIssue(error, 'reason');
  return isFailureReason(reason)
    ? new WorkspaceTextError(reason, detailIssue(error, 'current_version') ?? null)
    : error;
}

async function request<T>(endpoint: string, init: RequestInit = {}): Promise<T> {
  try {
    return await apiRequest<T>(endpoint, { ...init, silent: true });
  } catch (error) {
    throw asWorkspaceTextError(error);
  }
}

/** Reads `path` for editing. A file the editor cannot change still comes back, flagged with the reason. */
export async function readWorkspaceText(workspace: string, path: string): Promise<WorkspaceTextSnapshot> {
  const params = new URLSearchParams({ workspace, path });
  const payload = await request<SnapshotPayload>(`/files/browse/text?${params}`);
  return {
    path: payload.path,
    name: payload.name,
    content: payload.content,
    version: payload.version,
    size: payload.size,
    editable: payload.editable,
    readonlyReason: payload.readonly_reason,
    truncated: payload.truncated,
  };
}

/** Saves `content` over `path` if the file still has `baseVersion`; otherwise throws `version_conflict`. */
export async function saveWorkspaceText(
  workspace: string,
  path: string,
  content: string,
  baseVersion: string,
): Promise<WorkspaceTextWritten> {
  return request<WorkspaceTextWritten>('/files/browse/text', {
    method: 'PUT',
    body: JSON.stringify({ workspace, path, content_b64: encodeUtf8Base64(content), base_version: baseVersion }),
  });
}

/** Writes `content` to a new numbered file next to `path` ("notes (1).txt"); the original is never touched. */
export async function saveWorkspaceTextCopy(
  workspace: string,
  path: string,
  content: string,
): Promise<WorkspaceTextWritten> {
  return request<WorkspaceTextWritten>('/files/browse/text/copy', {
    method: 'POST',
    body: JSON.stringify({ workspace, path, content_b64: encodeUtf8Base64(content) }),
  });
}
