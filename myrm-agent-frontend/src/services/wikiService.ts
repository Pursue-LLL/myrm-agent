import { apiRequest } from '@/lib/api';

let scopedAgentId: string | undefined;

function wikiPath(path: string): string {
  if (!scopedAgentId) {
    return path;
  }
  const joiner = path.includes('?') ? '&' : '?';
  return `${path}${joiner}agent_id=${encodeURIComponent(scopedAgentId)}`;
}

export interface Concept {
  name: string;
  content: string;
}

export interface QueueStatus {
  stats: Record<string, number>;
  pending_items: Array<{
    id: number;
    source_path: string;
    file_type: string;
    status: string;
    created_at: string;
    updated_at: string;
  }>;
}

export interface PendingEdit {
  id: number;
  concept_name: string;
  proposed_content: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface PendingEditsResponse {
  stats: Record<string, number>;
  pending_edits: PendingEdit[];
}

export interface OperationResult {
  success: boolean;
  message: string;
}

export interface ConceptListResponse {
  concepts: string[];
  total: number;
  has_more: boolean;
}

export interface TreeNode {
  id: string;
  name: string;
  is_dir: boolean;
  children?: TreeNode[];
}

export interface ImportResultResponse {
  success: boolean;
  files_scanned: number;
  files_enqueued: number;
  message: string;
}

export interface ObsidianImportResultResponse {
  success: boolean;
  files_scanned: number;
  files_processed: number;
  files_skipped: number;
  tags_extracted: number;
  images_copied: number;
  message: string;
}

export const wikiService = {
  setAgentScope(agentId?: string | null): void {
    const trimmed = agentId?.trim();
    scopedAgentId = trimmed || undefined;
  },

  getTree: async (): Promise<TreeNode[]> => {
    return apiRequest<TreeNode[]>(wikiPath('/wiki/tree'));
  },

  createFolder: async (path: string): Promise<OperationResult> => {
    return apiRequest<OperationResult>(wikiPath('/wiki/tree/folder'), {
      method: 'POST',
      body: JSON.stringify({ path }),
    });
  },

  moveNode: async (sourcePath: string, targetPath: string): Promise<OperationResult> => {
    return apiRequest<OperationResult>(wikiPath('/wiki/tree/move'), {
      method: 'PUT',
      body: JSON.stringify({ source_path: sourcePath, target_path: targetPath }),
    });
  },

  deleteFolder: async (path: string): Promise<OperationResult> => {
    const params = new URLSearchParams();
    params.append('path', path);
    return apiRequest<OperationResult>(wikiPath(`/wiki/tree/folder?${params.toString()}`), {
      method: 'DELETE',
    });
  },

  listConcepts: async (query?: string, limit: number = 100, offset: number = 0): Promise<ConceptListResponse> => {
    const params = new URLSearchParams();
    if (query) params.append('query', query);
    params.append('limit', limit.toString());
    params.append('offset', offset.toString());
    return apiRequest<ConceptListResponse>(wikiPath(`/wiki/concepts?${params.toString()}`));
  },

  getConcept: async (name: string): Promise<Concept> => {
    return apiRequest<Concept>(wikiPath(`/wiki/concepts/${encodeURIComponent(name)}`));
  },

  updateConcept: async (name: string, content: string): Promise<OperationResult> => {
    return apiRequest<OperationResult>(wikiPath(`/wiki/concepts/${encodeURIComponent(name)}`), {
      method: 'PUT',
      body: JSON.stringify({ content }),
    });
  },

  deleteConcept: async (name: string): Promise<OperationResult> => {
    return apiRequest<OperationResult>(wikiPath(`/wiki/concepts/${encodeURIComponent(name)}`), {
      method: 'DELETE',
    });
  },

  getQueueStatus: async (): Promise<QueueStatus> => {
    return apiRequest<QueueStatus>(wikiPath('/wiki/queue'));
  },

  cancelQueue: async (): Promise<OperationResult> => {
    return apiRequest<OperationResult>(wikiPath('/wiki/queue/cancel'), {
      method: 'POST',
    });
  },

  retryFailedQueue: async (): Promise<OperationResult> => {
    return apiRequest<OperationResult>(wikiPath('/wiki/queue/retry'), {
      method: 'POST',
    });
  },

  getPendingEdits: async (): Promise<PendingEditsResponse> => {
    return apiRequest<PendingEditsResponse>(wikiPath('/wiki/pending'));
  },

  approveEdit: async (id: number, modifiedContent?: string): Promise<OperationResult> => {
    return apiRequest<OperationResult>(wikiPath(`/wiki/pending/${id}/approve`), {
      method: 'POST',
      body: modifiedContent !== undefined ? JSON.stringify({ modified_content: modifiedContent }) : undefined,
    });
  },

  rejectEdit: async (id: number): Promise<OperationResult> => {
    return apiRequest<OperationResult>(wikiPath(`/wiki/pending/${id}/reject`), {
      method: 'POST',
    });
  },

  ingestArtifact: async (artifactId: string, agentId?: string | null): Promise<OperationResult> => {
    const trimmedAgentId = agentId?.trim();
    const path =
      trimmedAgentId != null && trimmedAgentId.length > 0
        ? `/wiki/ingest?agent_id=${encodeURIComponent(trimmedAgentId)}`
        : wikiPath('/wiki/ingest');
    return apiRequest<OperationResult>(path, {
      method: 'POST',
      body: JSON.stringify({ artifact_id: artifactId }),
    });
  },

  importFolder: async (
    folderPath: string,
    extensions: string[] = ['.md', '.txt', '.org'],
    autoCompile: boolean = true,
  ): Promise<ImportResultResponse> => {
    return apiRequest<ImportResultResponse>(wikiPath('/wiki/import/folder'), {
      method: 'POST',
      body: JSON.stringify({
        folder_path: folderPath,
        extensions,
        auto_compile: autoCompile,
      }),
    });
  },

  importZip: async (
    file: File,
    extensions: string = '.md,.txt,.org',
    autoCompile: boolean = true,
  ): Promise<ImportResultResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    const params = new URLSearchParams();
    params.append('extensions', extensions);
    params.append('auto_compile', autoCompile.toString());
    return apiRequest<ImportResultResponse>(wikiPath(`/wiki/import/zip?${params.toString()}`), {
      method: 'POST',
      body: formData,
    });
  },

  importObsidianFolder: async (
    vaultPath: string,
    autoCompile: boolean = true,
  ): Promise<ObsidianImportResultResponse> => {
    return apiRequest<ObsidianImportResultResponse>(wikiPath('/wiki/import/obsidian'), {
      method: 'POST',
      body: JSON.stringify({ vault_path: vaultPath, auto_compile: autoCompile }),
    });
  },

  importObsidianZip: async (
    file: File,
    autoCompile: boolean = true,
  ): Promise<ObsidianImportResultResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    const params = new URLSearchParams();
    params.append('auto_compile', autoCompile.toString());
    return apiRequest<ObsidianImportResultResponse>(wikiPath(`/wiki/import/obsidian-zip?${params.toString()}`), {
      method: 'POST',
      body: formData,
    });
  },
};
