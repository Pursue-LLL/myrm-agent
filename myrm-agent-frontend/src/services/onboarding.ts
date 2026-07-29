import { apiRequest } from '@/lib/api';

export interface ReadinessResponse {
  provider: {
    is_ready: boolean;
    missing_items: string[];
    suggestions: string[];
  };
  search: {
    is_ready: boolean;
    missing_items?: string[];
    suggestions?: string[];
  };
  onboarding_completed: boolean;
  degraded?: boolean;
}

export async function getReadinessStatus(): Promise<ReadinessResponse> {
  return apiRequest<ReadinessResponse>('/config/readiness', { method: 'GET' });
}

export async function completeOnboarding(): Promise<{ success: boolean; message: string }> {
  return apiRequest<{ success: boolean; message: string }>('/config/onboarding/complete', { method: 'POST' });
}

export interface TelegramAssistantOnboardingRequest {
  botToken: string;
  webhookUrl?: string;
  assistantName?: string;
  assistantDescription?: string;
  assistantSystemPrompt?: string;
}

export interface TelegramAssistantOnboardingResponse {
  success: boolean;
  message: string;
  botUsername: string;
  agentId: string;
  agentName: string;
  channelEnabled: boolean;
  connected: boolean;
  status: string;
}

export async function applyTelegramAssistantOnboarding(
  payload: TelegramAssistantOnboardingRequest,
): Promise<TelegramAssistantOnboardingResponse> {
  return apiRequest<TelegramAssistantOnboardingResponse>('/config/onboarding/telegram-assistant/apply', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    silent: true,
  });
}

export interface SecondBrainChecklistItem {
  id: 'agent_tools' | 'cron_job' | 'vault_content' | 'provider_ready';
  ready: boolean;
}

export interface SecondBrainPresetStatus {
  applied: boolean;
  agent_id?: string | null;
  agent_name?: string | null;
  cron_job_id?: string | null;
  applied_at?: string | null;
  checklist: SecondBrainChecklistItem[];
}

export interface SecondBrainApplyResponse extends SecondBrainPresetStatus {
  success: boolean;
  message: string;
  agent_id: string;
  agent_name: string;
}

export async function getSecondBrainPresetStatus(): Promise<SecondBrainPresetStatus> {
  return apiRequest<SecondBrainPresetStatus>('/config/onboarding/second-brain/status', {
    method: 'GET',
  });
}

export async function applySecondBrainPreset(): Promise<SecondBrainApplyResponse> {
  return apiRequest<SecondBrainApplyResponse>('/config/onboarding/second-brain/apply', {
    method: 'POST',
    silent: true,
  });
}
