import { apiRequest } from '@/lib/api';

export interface DirectoryConfig {
  id: string;
  path: string;
  recursive: boolean;
  enabled: boolean;
  created_at: string;
}

export interface IndexStats {
  total_files: number;
  total_chunks: number;
  total_directories: number;
  status: 'idle' | 'indexing' | 'failed';
  last_indexed_at: string | null;
  indexing_progress: number;
  current_file: string | null;
  error_count: number;
}

export interface LocalFileSearchConfig {
  directories: DirectoryConfig[];
  stats: IndexStats;
}

const BASE = '/local-file-search';

export async function getLocalFileSearchConfig(): Promise<LocalFileSearchConfig> {
  return apiRequest<LocalFileSearchConfig>(BASE);
}

export async function addDirectory(path: string, recursive: boolean): Promise<DirectoryConfig> {
  return apiRequest<DirectoryConfig>(`${BASE}/directories`, {
    method: 'POST',
    body: JSON.stringify({ path, recursive }),
  });
}

export async function updateDirectory(
  id: string,
  updates: { enabled?: boolean; recursive?: boolean },
): Promise<DirectoryConfig> {
  return apiRequest<DirectoryConfig>(`${BASE}/directories/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(updates),
  });
}

export async function removeDirectory(id: string): Promise<void> {
  await apiRequest(`${BASE}/directories/${id}`, {
    method: 'DELETE',
  });
}

export async function triggerIndex(): Promise<IndexStats> {
  return apiRequest<IndexStats>(`${BASE}/index`, {
    method: 'POST',
  });
}

export async function getIndexStats(): Promise<IndexStats> {
  return apiRequest<IndexStats>(`${BASE}/stats`);
}
