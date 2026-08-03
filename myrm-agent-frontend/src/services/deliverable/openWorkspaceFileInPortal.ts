/**
 * SSOT: open a workspace file in ArtifactPortal via /files/browse/content.
 *
 * [INPUT] browse path, chat/workspace context, pre-built Artifact shell.
 * [OUTPUT] Portal side effects (open tab, load content, errors).
 * [POS] Shared by DeliverableReferenceLink, ActiveWorkingMemoryPanel, openWorkspaceDeliverable.
 */

import { fetchWithTimeout } from '@/lib/api';
import useArtifactPortalStore, { type OpenArtifactTabOptions } from '@/store/useArtifactPortalStore';
import type { Artifact } from '@/store/chat/types/artifacts';
import useChatStore from '@/store/useChatStore';

export type FetchWorkspaceBrowseResult =
  | { ok: true; content: string; truncated: boolean }
  | { ok: false; status: number; detail: string };

export async function resolveWorkspaceDirForBrowse(
  chatId?: string,
  existingDir?: string | null,
  onResolved?: (dir: string) => void,
): Promise<string | undefined> {
  let dir = existingDir?.trim() || undefined;
  if (!dir && chatId) {
    try {
      const { getChatDetail } = await import('@/services/chat');
      const detail = await getChatDetail(chatId, true);
      const w = detail.chat.workspace_dir;
      if (typeof w === 'string' && w.trim().length > 0) {
        dir = w.trim();
        onResolved?.(dir);
      }
    } catch {
      /* browse/content resolves workspace via chat_id */
    }
  }
  return dir;
}

export async function fetchWorkspaceBrowseContent(
  browsePath: string,
  options: { chatId?: string; workspaceDir?: string },
): Promise<FetchWorkspaceBrowseResult> {
  const qp = new URLSearchParams();
  qp.set('path', browsePath);
  if (options.workspaceDir) {
    qp.set('workspace', options.workspaceDir);
  }
  if (options.chatId) {
    qp.set('chat_id', options.chatId);
  }

  try {
    const res = await fetchWithTimeout(`/files/browse/content?${qp.toString()}`);
    if (!res.ok) {
      const detail = await res.text().catch(() => '');
      return { ok: false, status: res.status, detail: detail || `HTTP ${res.status}` };
    }
    const truncated = res.headers.get('X-Content-Truncated') === 'true';
    const content = await res.text();
    return { ok: true, content, truncated };
  } catch (err) {
    return {
      ok: false,
      status: 0,
      detail: err instanceof Error ? err.message : 'Unknown error',
    };
  }
}

export interface OpenWorkspaceFileInPortalParams {
  artifact: Artifact;
  browsePath: string;
  chatId?: string;
  workspaceDir?: string;
  portalOpenOptions?: OpenArtifactTabOptions;
  formatTruncated?: (content: string) => string;
  formatNotFound?: () => string;
  onMissingContext?: () => void;
}

export async function openWorkspaceFileInPortal({
  artifact,
  browsePath,
  chatId,
  workspaceDir,
  portalOpenOptions,
  formatTruncated,
  formatNotFound,
  onMissingContext,
}: OpenWorkspaceFileInPortalParams): Promise<void> {
  const { openArtifact, setContent, setContentLoading, setError, clearError } =
    useArtifactPortalStore.getState();

  openArtifact(artifact, portalOpenOptions);
  setContentLoading(true);
  clearError();

  const dir = await resolveWorkspaceDirForBrowse(chatId, workspaceDir, (resolved) => {
    useChatStore.getState().setWorkspaceDir(resolved);
  });

  if (!dir && !chatId) {
    setContentLoading(false);
    if (onMissingContext) {
      onMissingContext();
      return;
    }
    setError({
      type: ArtifactErrorType.Unknown,
      messageKey: 'errors.unknown',
      details: 'Missing chat context for workspace file preview',
      retryable: false,
    });
    return;
  }

  try {
    const result = await fetchWorkspaceBrowseContent(browsePath, {
      chatId,
      workspaceDir: dir,
    });

    if (!result.ok) {
      if (result.status === 404 && formatNotFound) {
        setContent(formatNotFound());
        return;
      }
      setError({
        type: result.status === 404 ? ArtifactErrorType.NotFound : ArtifactErrorType.Unknown,
        messageKey: result.status === 404 ? 'errors.notFound' : 'errors.unknown',
        details: result.detail,
        retryable: result.status >= 500,
      });
      return;
    }

    let content = result.content;
    if (result.truncated && formatTruncated) {
      content = formatTruncated(content);
    }
    setContent(content);
  } finally {
    setContentLoading(false);
  }
}
