/**
 * [INPUT]
 * - apiRequest from '@/lib/api'
 * - UIRequestItem, UIResponsePayload from '@/components/features/extension-ui/extensionUITypes'
 *
 * [OUTPUT]
 * - fetchPendingUIRequests, submitUIResponse, cancelUIRequest
 *
 * [POS]
 * Client HTTP API service for Extension UI reverse push sub-protocol (Item 28).
 * Strictly typed, zero `any`, file length < 80 lines.
 */

import { apiRequest } from '@/lib/api';
import type { UIRequestItem, UIResponsePayload } from '@/components/features/extension-ui/extensionUITypes';

interface FetchUIRequestsResponse {
  requests: UIRequestItem[];
  count: number;
}

interface SubmitUIResponseResult {
  resolved: boolean;
  request_id: string;
}

interface CancelUIResponseResult {
  cancelled: boolean;
  request_id: string;
}

export async function fetchPendingUIRequests(chatId: string): Promise<UIRequestItem[]> {
  try {
    const res = await apiRequest<FetchUIRequestsResponse>(`/chats/${chatId}/ui-requests`);
    return res?.requests ?? [];
  } catch (err) {
    console.error('[extensionUIService] Failed to fetch pending UI requests', err);
    return [];
  }
}

export async function submitUIResponse(
  chatId: string,
  requestId: string,
  payload: UIResponsePayload,
): Promise<SubmitUIResponseResult> {
  return apiRequest<SubmitUIResponseResult>(`/chats/${chatId}/ui-response/${requestId}`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function cancelUIRequest(
  chatId: string,
  requestId: string,
  reason: string = 'Interaction cancelled by operator',
): Promise<CancelUIResponseResult> {
  return apiRequest<CancelUIResponseResult>(`/chats/${chatId}/ui-cancel/${requestId}`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  });
}
