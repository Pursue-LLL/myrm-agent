/**
 * [INPUT]
 * - process.env.NEXT_PUBLIC_CP_API_URL (POS: Control Plane 基础 URL)
 *
 * [OUTPUT]
 * - fetchEntitlements: 拉取 CP 权益 + WU 余额
 * - fetchWorkUnitEstimate: 拉取 CP 消息 WU 预估值
 *
 * [POS]
 * 前端 Control Plane Billing API 薄封装（仅 SaaS Sandbox）。
 */

export interface EntitlementSnapshot {
  user_id: string;
  plan: 'free' | 'companion' | 'pro' | 'max' | 'team';
  status: string;
  balance_wu: number;
  subscription_wu: number;
  topup_wu: number;
  monthly_allowance_wu: number;
  daily_refresh_remaining_wu: number;
  period_end: number | null;
  stripe_customer_id?: string | null;
  enable_cron: boolean;
  enable_public_ingress: boolean;
  max_cron_triggers: number;
  enable_subagent: boolean;
  enable_vnc: boolean;
  idle_sleep_seconds: number;
  cpu_limit: number;
  memory_mb: number;
  free_models: string[];
}

export interface WorkUnitEstimateResponse {
  estimated_wu: number;
  balance_wu: number;
  remaining_after_wu: number;
}

export interface WorkUnitEstimateRequest {
  message_length: number;
  has_attachments?: boolean;
  action_mode?: string;
}

export function getCpApiBaseUrl(): string {
  return (process.env.NEXT_PUBLIC_CP_API_URL || 'http://127.0.0.1:8003').replace(/\/+$/, '');
}

export async function fetchEntitlements(token: string): Promise<EntitlementSnapshot> {
  const response = await fetch(`${getCpApiBaseUrl()}/api/billing/entitlements`, {
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    cache: 'no-store',
  });
  if (!response.ok) {
    throw new Error(`Failed to fetch entitlements: ${response.status}`);
  }
  return response.json();
}

export async function fetchWorkUnitEstimate(
  token: string,
  body: WorkUnitEstimateRequest,
): Promise<WorkUnitEstimateResponse> {
  const response = await fetch(`${getCpApiBaseUrl()}/api/billing/estimate`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
    cache: 'no-store',
  });
  if (!response.ok) {
    throw new Error(`Failed to fetch WU estimate: ${response.status}`);
  }
  return response.json();
}
