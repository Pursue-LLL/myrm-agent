/**
 * Subscription and Quota Hooks
 *
 * 提供订阅状态和配额使用情况的 hooks。
 *
 * 架构说明：
 * - 使用 SWR 进行数据缓存和自动重新验证
 * - suspense: false - 关键配置，防止 SSR 时组件 suspend 导致 hydration 不匹配
 * - isAuthenticated - 使用正确的属性名（不是 isLoggedIn）
 * - 错误处理优化：静默处理网络错误，禁用不必要的重试
 *
 * Hydration 安全：
 * 所有 SWR 配置都显式设置 suspense: false，确保组件在 SSR 和 CSR 时行为一致
 *
 * 错误处理策略：
 * - 网络错误（服务不可用）：静默处理，使用降级数据
 * - HTTP 错误（4xx/5xx）：记录日志，但不中断用户体验
 * - 禁用自动重试：避免不必要的网络请求
 */

import useSWR from 'swr';
import useAuthStore from '@/store/useAuthStore';
import { isLocalMode, isSandbox } from '@/lib/deploy-mode';
import { type EntitlementSnapshot } from '@/lib/cp-billing';
import { useEntitlements } from '@/hooks/useEntitlements';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8080/api/v1';

// Error types for better error handling
const ERROR_TYPES = {
  NETWORK: 'NETWORK_ERROR',
  HTTP: 'HTTP_ERROR',
  UNKNOWN: 'UNKNOWN_ERROR',
} as const;

type ErrorType = (typeof ERROR_TYPES)[keyof typeof ERROR_TYPES];

class SubscriptionError extends Error {
  constructor(
    public type: ErrorType,
    message: string,
    public statusCode?: number,
  ) {
    super(message);
    this.name = 'SubscriptionError';
  }
}

// Types
export type PlanType = 'free' | 'companion' | 'plus' | 'pro' | 'max' | 'team';

export interface SubscriptionStatus {
  plan_type: PlanType;
  billing_cycle: 'monthly' | 'yearly';
  status: 'active' | 'trialing' | 'cancelled' | 'past_due' | 'expired';
  billing_customer_id?: string | null;
  current_period_start: string | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  cancelled_at: string | null;
  /** SaaS WU balance (sandbox only) */
  balance_wu?: number;
  subscription_wu?: number;
  topup_wu?: number;
  monthly_allowance_wu?: number;
}

export interface TokenUsage {
  used: number;
  limit: number;
  remaining: number;
  percentage: number;
}

export interface CountUsage {
  used: number;
  limit: number;
  remaining: number;
}

export interface QuotaFeatures {
  has_priority_queue: boolean;
  has_config_sync: boolean;
  has_advanced_models: boolean;
}

export interface QuotaLimits {
  max_memories: number;
  max_skills: number;
  max_skill_storage_mb: number;
  max_agents: number;
}

export interface QuotaUsage {
  plan_type: 'free' | 'pro';
  tokens: TokenUsage;
  chats: CountUsage;
  searches: CountUsage;
  features: QuotaFeatures;
  limits: QuotaLimits;
  reset_at: string;
}

/**
 * Fetcher with auth and enhanced error handling
 *
 * Error handling strategy:
 * - Network errors (connection refused, timeout): throw NETWORK_ERROR - will be silently handled
 * - HTTP errors (4xx/5xx): throw HTTP_ERROR with status code - will be logged
 *
 * @param url - API endpoint URL
 * @returns Promise with typed response data
 * @throws SubscriptionError with specific error type
 */
async function fetchWithAuth<T>(url: string): Promise<T> {
  try {
    const token = localStorage.getItem('auth_token');
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    };

    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(url, { headers });

    if (!response.ok) {
      // HTTP error (4xx/5xx)
      throw new SubscriptionError(ERROR_TYPES.HTTP, `HTTP ${response.status}: ${response.statusText}`, response.status);
    }

    return response.json();
  } catch (error) {
    // Network error detection
    if (
      error instanceof TypeError &&
      (error.message.includes('Failed to fetch') ||
        error.message.includes('NetworkError') ||
        error.message.includes('Network request failed'))
    ) {
      // Silently handle network errors - service unavailable
      console.warn('[Subscription Service] Service unavailable, using fallback data | 订阅服务不可用，使用降级数据');
      throw new SubscriptionError(ERROR_TYPES.NETWORK, 'Subscription service is currently unavailable');
    }

    // Re-throw SubscriptionError as-is
    if (error instanceof SubscriptionError) {
      throw error;
    }

    // Unknown error
    throw new SubscriptionError(ERROR_TYPES.UNKNOWN, error instanceof Error ? error.message : 'Unknown error occurred');
  }
}

function mapCpStatus(status: string): SubscriptionStatus['status'] {
  if (status === 'trialing') return 'trialing';
  if (status === 'cancelled') return 'cancelled';
  if (status === 'past_due') return 'past_due';
  if (status === 'expired') return 'expired';
  return 'active';
}

function mapEntitlementsToSubscription(snapshot: EntitlementSnapshot): SubscriptionStatus {
  return {
    plan_type: snapshot.plan,
    billing_cycle: 'monthly',
    status: mapCpStatus(snapshot.status),
    billing_customer_id: snapshot.billing_customer_id ?? null,
    current_period_start: null,
    current_period_end: snapshot.period_end ? new Date(snapshot.period_end * 1000).toISOString() : null,
    cancel_at_period_end: snapshot.status === 'cancelled',
    cancelled_at:
      snapshot.status === 'cancelled' && snapshot.period_end
        ? new Date(snapshot.period_end * 1000).toISOString()
        : null,
    balance_wu: snapshot.balance_wu,
    subscription_wu: snapshot.subscription_wu,
    topup_wu: snapshot.topup_wu,
    monthly_allowance_wu: snapshot.monthly_allowance_wu,
    free_models: snapshot.free_models,
  };
}

/**
 * Hook to get subscription status
 *
 * Optimizations:
 * - Disabled auto-retry to prevent unnecessary network requests
 * - Graceful fallback to Free plan when service is unavailable
 * - Silent error handling for network issues
 */
export function useSubscription() {
  const { isAuthenticated } = useAuthStore();
  const local = isLocalMode();
  const sandbox = isSandbox();
  const {
    entitlements,
    isLoading: entitlementsLoading,
    error: entitlementsError,
    refresh: refreshEntitlements,
  } = useEntitlements();

  const legacyKey = isAuthenticated && !local && !sandbox ? `${API_BASE_URL}/subscription/status` : null;

  const {
    data: legacyData,
    error: legacyError,
    isLoading: legacyLoading,
    mutate: refreshLegacy,
  } = useSWR<SubscriptionStatus>(legacyKey, fetchWithAuth, {
    revalidateOnFocus: false,
    revalidateOnReconnect: false,
    dedupingInterval: 60000, // Cache for 1 minute
    suspense: false, // 禁用 suspense 模式，防止 SSR hydration 不匹配
    shouldRetryOnError: false, // 禁用自动重试
    errorRetryCount: 0, // 不重试
    onError: (err: Error) => {
      // Only log non-network errors
      if (err instanceof SubscriptionError) {
        if (err.type === ERROR_TYPES.NETWORK) {
          // Network error - silently handled
          return;
        }
        if (err.type === ERROR_TYPES.HTTP) {
          // HTTP error - log for debugging
          console.warn(`[Subscription API] HTTP Error ${err.statusCode}: ${err.message}`);
          return;
        }
      }
      // Unknown error
      console.error('[Subscription API] Unexpected error:', err);
    },
  });

  const cpSubscription = sandbox && entitlements ? mapEntitlementsToSubscription(entitlements) : null;

  const data = sandbox ? cpSubscription : legacyData;
  const error = sandbox ? entitlementsError : legacyError;
  const isLoading = sandbox ? entitlementsLoading : legacyLoading;
  const mutate = sandbox ? refreshEntitlements : refreshLegacy;

  // Fallback to Free plan if no data available
  const subscription: SubscriptionStatus = data || {
    plan_type: 'free',
    billing_cycle: 'monthly',
    status: 'active',
    billing_customer_id: null,
    current_period_start: null,
    current_period_end: null,
    cancel_at_period_end: false,
    cancelled_at: null,
  };

  const isPaidPlan = Boolean(data && data.plan_type !== 'free' && data.status === 'active');
  const isPro = isPaidPlan;

  return {
    subscription,
    isPro,
    isPaidPlan,
    isLoading,
    error,
    refresh: mutate,
  };
}

function mapEntitlementsToQuotaUsage(snapshot: EntitlementSnapshot): QuotaUsage {
  const used = Math.max(0, snapshot.monthly_allowance_wu - snapshot.balance_wu);
  const limit = snapshot.monthly_allowance_wu;
  const remaining = snapshot.balance_wu;
  const percentage = limit > 0 ? Math.min(100, (used / limit) * 100) : 0;

  return {
    plan_type: snapshot.plan === 'free' ? 'free' : 'pro',
    tokens: { used, limit, remaining, percentage },
    chats: { used: 0, limit: 0, remaining: 0 },
    searches: { used: 0, limit: 0, remaining: 0 },
    features: {
      has_priority_queue: snapshot.plan !== 'free',
      has_config_sync: snapshot.plan !== 'free',
      has_advanced_models: snapshot.plan === 'pro' || snapshot.plan === 'max',
    },
    limits: {
      max_memories: 100,
      max_skills: snapshot.plan === 'free' ? 1 : 10,
      max_skill_storage_mb: snapshot.plan === 'free' ? 10 : 100,
      max_agents: snapshot.plan === 'free' ? 1 : 5,
    },
    reset_at: snapshot.period_end ? new Date(snapshot.period_end * 1000).toISOString() : new Date().toISOString(),
  };
}

/**
 * Hook to get quota usage (Sandbox: CP Work Units via entitlements; legacy: server quota API).
 *
 * Optimizations:
 * - Reduced refresh interval to avoid excessive requests
 * - Disabled auto-retry on error
 * - Graceful fallback to default Free plan quota
 * - Silent error handling for network issues
 */
export function useQuota() {
  const { isAuthenticated } = useAuthStore();
  const local = isLocalMode();
  const sandbox = isSandbox();
  const { entitlements, isLoading: entitlementsLoading, refresh: refreshEntitlements } = useEntitlements();

  const legacyKey = isAuthenticated && !local && !sandbox ? `${API_BASE_URL}/subscription/quota` : null;

  const { data, error, isLoading, mutate } = useSWR<QuotaUsage>(legacyKey, fetchWithAuth, {
    revalidateOnFocus: false, // 关闭焦点时重新验证，避免频繁请求
    revalidateOnReconnect: false, // 关闭重连时重新验证
    dedupingInterval: 10000, // 增加到 10 秒，减少请求频率
    refreshInterval: 60000, // 增加到 60 秒，降低后台刷新频率
    suspense: false, // 禁用 suspense 模式，防止 SSR hydration 不匹配
    shouldRetryOnError: false, // 禁用自动重试
    errorRetryCount: 0, // 不重试
    onError: (err: Error) => {
      // Only log non-network errors
      if (err instanceof SubscriptionError) {
        if (err.type === ERROR_TYPES.NETWORK) {
          // Network error - silently handled
          return;
        }
        if (err.type === ERROR_TYPES.HTTP) {
          // HTTP error - log for debugging
          console.warn(`[Quota API] HTTP Error ${err.statusCode}: ${err.message}`);
          return;
        }
      }
      // Unknown error
      console.error('[Quota API] Unexpected error:', err);
    },
  });

  // Default values for fallback (Free plan quota)
  const defaultQuota: QuotaUsage = {
    plan_type: 'free',
    tokens: { used: 0, limit: 1000000, remaining: 1000000, percentage: 0 },
    chats: { used: 0, limit: 50, remaining: 50 },
    searches: { used: 0, limit: 10, remaining: 10 },
    features: {
      has_priority_queue: false,
      has_config_sync: false,
      has_advanced_models: false,
    },
    limits: {
      max_memories: 100,
      max_skills: 1,
      max_skill_storage_mb: 10,
      max_agents: 1,
    },
    reset_at: new Date().toISOString(),
  };

  return {
    quota: sandbox && entitlements ? mapEntitlementsToQuotaUsage(entitlements) : data || defaultQuota,
    isLoading: sandbox ? entitlementsLoading : isLoading,
    error: sandbox ? null : error,
    refresh: sandbox ? refreshEntitlements : mutate,
  };
}
