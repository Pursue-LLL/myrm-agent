/**
 * [INPUT]
 * - @/lib/api::API_BASE_URL, apiRequest (POS: API 请求层)
 *
 * [OUTPUT]
 * - Canvas CRUD / snapshot / selection API functions
 *
 * [POS]
 * Infinite canvas workspace API service layer.
 */

import { API_BASE_URL, apiRequest } from '@/lib/api';

const PREFIX = '/canvas';

export interface CanvasItem {
  id: string;
  name: string;
  agent_id: string | null;
  chat_id: string | null;
  thumbnail: string | null;
  created_at: string | null;
  updated_at: string | null;
}

interface ApiResponse<T> {
  success: boolean;
  data: T;
}

// ── CRUD ─────────────────────────────────────────────────────────────

export async function listCanvases(): Promise<CanvasItem[]> {
  const res = await apiRequest(`${API_BASE_URL}${PREFIX}`);
  const json: ApiResponse<CanvasItem[]> = await res.json();
  return json.data;
}

export async function createCanvas(
  name: string = 'Untitled Canvas',
  agentId?: string,
  chatId?: string,
): Promise<CanvasItem> {
  const res = await apiRequest(`${API_BASE_URL}${PREFIX}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, agent_id: agentId, chat_id: chatId }),
  });
  const json: ApiResponse<CanvasItem> = await res.json();
  return json.data;
}

export async function getCanvas(canvasId: string): Promise<CanvasItem> {
  const res = await apiRequest(`${API_BASE_URL}${PREFIX}/${canvasId}`);
  const json: ApiResponse<CanvasItem> = await res.json();
  return json.data;
}

export async function updateCanvas(
  canvasId: string,
  updates: Partial<Pick<CanvasItem, 'name' | 'agent_id' | 'chat_id' | 'thumbnail'>>,
): Promise<void> {
  await apiRequest(`${API_BASE_URL}${PREFIX}/${canvasId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
}

export async function deleteCanvas(canvasId: string): Promise<void> {
  await apiRequest(`${API_BASE_URL}${PREFIX}/${canvasId}`, { method: 'DELETE' });
}

// ── Snapshot ─────────────────────────────────────────────────────────

export async function saveSnapshot(
  canvasId: string,
  snapshot: Record<string, unknown>,
  thumbnail?: string,
): Promise<void> {
  await apiRequest(`${API_BASE_URL}${PREFIX}/${canvasId}/snapshot`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ snapshot, thumbnail }),
  });
}

export async function loadSnapshot(
  canvasId: string,
): Promise<Record<string, unknown> | null> {
  const res = await apiRequest(`${API_BASE_URL}${PREFIX}/${canvasId}/snapshot`);
  const json: ApiResponse<{ snapshot: Record<string, unknown> | null }> = await res.json();
  return json.data.snapshot;
}

// ── Selection ────────────────────────────────────────────────────────

export async function saveSelection(
  canvasId: string,
  selectedShapes: Record<string, unknown>[],
): Promise<void> {
  await apiRequest(`${API_BASE_URL}${PREFIX}/${canvasId}/selection`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ selected_shapes: selectedShapes }),
  });
}

export async function loadSelection(
  canvasId: string,
): Promise<{ selectedShapes: Record<string, unknown>[]; updatedAt: string | null }> {
  const res = await apiRequest(`${API_BASE_URL}${PREFIX}/${canvasId}/selection`);
  const json: ApiResponse<{ selectedShapes: Record<string, unknown>[]; updatedAt: string | null }> =
    await res.json();
  return json.data;
}

// ── SSE ──────────────────────────────────────────────────────────────

export function createCanvasEventSource(canvasId: string): EventSource {
  return new EventSource(`${API_BASE_URL}${PREFIX}/${canvasId}/events`);
}
