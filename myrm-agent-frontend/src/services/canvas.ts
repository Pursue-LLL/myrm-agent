/**
 * [INPUT]
 * - @/lib/api::apiRequest, getApiUrl (POS: API 请求层)
 *
 * [OUTPUT]
 * - Canvas CRUD / snapshot / selection API functions
 *
 * [POS]
 * Infinite canvas workspace API service layer.
 */

import { apiRequest, getApiUrl } from '@/lib/api';

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

// ── CRUD ─────────────────────────────────────────────────────────────

export async function listCanvases(): Promise<CanvasItem[]> {
  return apiRequest<CanvasItem[]>(PREFIX);
}

export async function createCanvas(
  name: string = 'Untitled Canvas',
  agentId?: string,
  chatId?: string,
): Promise<CanvasItem> {
  return apiRequest<CanvasItem>(PREFIX, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, agent_id: agentId, chat_id: chatId }),
  });
}

export async function getCanvas(canvasId: string): Promise<CanvasItem> {
  return apiRequest<CanvasItem>(`${PREFIX}/${canvasId}`);
}

export async function updateCanvas(
  canvasId: string,
  updates: Partial<Pick<CanvasItem, 'name' | 'agent_id' | 'chat_id' | 'thumbnail'>>,
): Promise<void> {
  await apiRequest(`${PREFIX}/${canvasId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
}

export async function deleteCanvas(canvasId: string): Promise<void> {
  await apiRequest(`${PREFIX}/${canvasId}`, { method: 'DELETE' });
}

// ── Snapshot ─────────────────────────────────────────────────────────

export async function saveSnapshot(
  canvasId: string,
  snapshot: Record<string, unknown>,
  thumbnail?: string,
): Promise<void> {
  await apiRequest(`${PREFIX}/${canvasId}/snapshot`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ snapshot, thumbnail }),
  });
}

export async function loadSnapshot(
  canvasId: string,
): Promise<Record<string, unknown> | null> {
  const data = await apiRequest<{ snapshot: Record<string, unknown> | null }>(
    `${PREFIX}/${canvasId}/snapshot`,
  );
  return data.snapshot;
}

// ── Selection ────────────────────────────────────────────────────────

export async function saveSelection(
  canvasId: string,
  selectedShapes: Record<string, unknown>[],
): Promise<void> {
  await apiRequest(`${PREFIX}/${canvasId}/selection`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ selected_shapes: selectedShapes }),
  });
}

export async function loadSelection(
  canvasId: string,
): Promise<{ selectedShapes: Record<string, unknown>[]; updatedAt: string | null }> {
  return apiRequest<{ selectedShapes: Record<string, unknown>[]; updatedAt: string | null }>(
    `${PREFIX}/${canvasId}/selection`,
  );
}

// ── SSE ──────────────────────────────────────────────────────────────

export function createCanvasEventSource(canvasId: string): EventSource {
  return new EventSource(getApiUrl(`${PREFIX}/${canvasId}/events`));
}
