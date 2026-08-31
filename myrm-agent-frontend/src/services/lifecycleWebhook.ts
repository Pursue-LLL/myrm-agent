import { apiRequest } from '@/lib/api';

export interface LifecycleWebhook {
  id: string;
  name: string;
  url: string;
  secret?: string | null;
  has_secret?: boolean;
  events: string[];
  agent_id?: string | null;
  is_active: boolean;
  timeout_seconds: number;
  last_delivery_at?: string | null;
  last_delivery_status?: number | null;
  last_error?: string | null;
  created_at: string;
  updated_at: string;
}

export interface LifecycleWebhookCreateInput {
  name: string;
  url: string;
  secret?: string | null;
  events: string[];
  agent_id?: string | null;
  is_active?: boolean;
  timeout_seconds?: number;
}

export interface LifecycleWebhookUpdateInput {
  name?: string;
  url?: string;
  secret?: string | null;
  events?: string[];
  agent_id?: string | null;
  clear_agent_scope?: boolean;
  is_active?: boolean;
  timeout_seconds?: number;
}

export interface WebhookPingInput {
  url: string;
  secret?: string | null;
  timeout_seconds?: number;
}

export interface WebhookPingResult {
  success: boolean;
  status_code?: number | null;
  latency_ms: number;
  error?: string | null;
}

export async function listLifecycleWebhooks(): Promise<LifecycleWebhook[]> {
  return apiRequest<LifecycleWebhook[]>('/lifecycle-webhooks');
}

export async function createLifecycleWebhook(input: LifecycleWebhookCreateInput): Promise<LifecycleWebhook> {
  return apiRequest<LifecycleWebhook>('/lifecycle-webhooks', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export async function updateLifecycleWebhook(
  id: string,
  input: LifecycleWebhookUpdateInput,
): Promise<LifecycleWebhook> {
  return apiRequest<LifecycleWebhook>(`/lifecycle-webhooks/${id}`, {
    method: 'PUT',
    body: JSON.stringify(input),
  });
}

export async function deleteLifecycleWebhook(id: string): Promise<void> {
  return apiRequest<void>(`/lifecycle-webhooks/${id}`, {
    method: 'DELETE',
  });
}

export async function pingLifecycleWebhook(input: WebhookPingInput): Promise<WebhookPingResult> {
  return apiRequest<WebhookPingResult>('/lifecycle-webhooks/ping', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export async function pingSavedLifecycleWebhook(webhookId: string): Promise<WebhookPingResult> {
  return apiRequest<WebhookPingResult>(`/lifecycle-webhooks/${webhookId}/ping`, {
    method: 'POST',
  });
}
