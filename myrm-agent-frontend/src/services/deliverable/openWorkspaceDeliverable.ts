/**
 * Open a workspace deliverable in ArtifactPortal (browse/content + chat_id SSOT).
 *
 * [INPUT] workspace-relative path, optional chatId / workspaceDir.
 * [OUTPUT] Opens portal tab via openWorkspaceFileInPortal (side effect).
 * [POS] Used by DeliverableReferenceLink.
 */

import type { Artifact, ArtifactType } from '@/store/chat/types/artifacts';
import { openWorkspaceFileInPortal } from '@/services/deliverable/openWorkspaceFileInPortal';
import useArtifactPortalStore from '@/store/useArtifactPortalStore';

function inferArtifactType(filename: string): ArtifactType {
  const ext = filename.split('.').pop()?.toLowerCase() ?? '';
  const map: Record<string, ArtifactType> = {
    xlsx: 'spreadsheet',
    xls: 'spreadsheet',
    csv: 'spreadsheet',
    pptx: 'presentation',
    ppt: 'presentation',
    docx: 'word_document',
    doc: 'word_document',
    pdf: 'pdf',
    html: 'html',
    htm: 'html',
    svg: 'svg',
    png: 'image',
    jpg: 'image',
    jpeg: 'image',
    gif: 'image',
    webp: 'image',
    mp4: 'video',
    webm: 'video',
    md: 'document',
    txt: 'document',
    json: 'document',
  };
  return map[ext] ?? 'document';
}

function inferContentType(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase() ?? '';
  const mime: Record<string, string> = {
    md: 'text/markdown',
    txt: 'text/plain',
    json: 'application/json',
    pdf: 'application/pdf',
    html: 'text/html',
    csv: 'text/csv',
  };
  return mime[ext] ?? 'text/plain';
}

export interface OpenWorkspaceDeliverableParams {
  path: string;
  chatId?: string;
  workspaceDir?: string;
}

export async function openWorkspaceDeliverable({
  path,
  chatId,
  workspaceDir,
}: OpenWorkspaceDeliverableParams): Promise<void> {
  const browsePath = path.startsWith('workspace/') ? path.slice('workspace/'.length) : path;
  const filename = browsePath.split('/').pop() ?? browsePath;
  const artifactId = `ws-${browsePath}`;

  const artifact: Artifact = {
    id: artifactId,
    filename,
    type: inferArtifactType(filename),
    content_type: inferContentType(filename),
    size: 0,
    preview_url: '',
    download_url: '',
    file_path: browsePath,
  };

  await openWorkspaceFileInPortal({
    artifact,
    browsePath,
    chatId,
    workspaceDir,
    formatTruncated: (content) => `/* [Warning] File truncated to first 1MB */\n\n${content}`,
  });
}

export async function openArtifactDeliverable(artifact: Artifact): Promise<void> {
  useArtifactPortalStore.getState().openArtifact(artifact);
}
