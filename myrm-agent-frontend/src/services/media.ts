import { apiRequest, getApiUrl } from '@/lib/api';

export interface MediaItem {
  id: string;
  media_type: string;
  source: string;
  prompt: string | null;
  model: string | null;
  resolution: string | null;
  content_type: string;
  file_size: number;
  tags: string[];
  session_id: string | null;
  batch_job_id: string | null;
  thumbnail_url: string | null;
  created_at: string;
}

export interface MediaListResponse {
  items: MediaItem[];
  next_cursor: string | null;
  total: number;
}

export interface MediaQueryParams {
  media_type?: string;
  tags?: string;
  keyword?: string;
  session_id?: string;
  batch_job_id?: string;
  before?: string;
  after?: string;
  cursor?: string;
  limit?: number;
}

export async function fetchMediaList(params: MediaQueryParams = {}): Promise<MediaListResponse> {
  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      searchParams.set(key, String(value));
    }
  }
  const query = searchParams.toString();
  return apiRequest<MediaListResponse>(`/media${query ? `?${query}` : ''}`);
}

export async function fetchMediaTags(): Promise<string[]> {
  return apiRequest<string[]>('/media/tags');
}

export async function fetchMediaItem(mediaId: string): Promise<MediaItem> {
  return apiRequest<MediaItem>(`/media/${mediaId}`);
}

export async function updateMediaTags(mediaId: string, tags: string[]): Promise<MediaItem> {
  return apiRequest<MediaItem>(`/media/${mediaId}/tags`, {
    method: 'PUT',
    body: JSON.stringify({ tags }),
  });
}

export async function deleteMedia(mediaId: string): Promise<void> {
  await apiRequest(`/media/${mediaId}`, { method: 'DELETE' });
}

export async function batchDeleteMedia(ids: string[]): Promise<{ deleted: number }> {
  return apiRequest<{ deleted: number }>('/media/batch/delete', {
    method: 'POST',
    body: JSON.stringify({ ids }),
  });
}

export async function batchUpdateTags(ids: string[], tags: string[]): Promise<{ updated: number }> {
  return apiRequest<{ updated: number }>('/media/batch/tags', {
    method: 'PUT',
    body: JSON.stringify({ ids, tags }),
  });
}

export function getMediaFileUrl(mediaId: string): string {
  return getApiUrl(`/media/${mediaId}/file`);
}

export function getMediaThumbnailUrl(mediaId: string): string {
  return getApiUrl(`/media/${mediaId}/thumbnail`);
}
