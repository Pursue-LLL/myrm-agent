/**
 * [POS]
 * Chat SSE event handler slice (rateLimitEvents).
 */

import type { StreamCtx, StreamTurn } from "../streamContext";
import { done } from "../streamContext";
export async function rateLimitEvents(ctx: StreamCtx): Promise<StreamTurn | null> {
  const { data } = ctx;
  if (data.type === 'rate_limit_updated') {
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('rate_limit_updated'));
    }
    return done(ctx);
  }

  if (data.type === 'rate_limit_warning') {
    const payload = data.data as { provider: string; model: string; usage_pct: number };
    if (payload) {
      const pct = Math.round(payload.usage_pct * 100);
      const lang = typeof document !== 'undefined' ? document.documentElement.lang : 'en';
      const toastMessage = lang?.startsWith('zh')
        ? `${payload.provider} (${payload.model}) 速率限制已达 ${pct}%。Agent 可能会放缓速度。`
        : `Rate limit usage for ${payload.provider} (${payload.model}) is at ${pct}%. Agent may slow down.`;

      import('@/lib/utils/toast').then(({ toast }) => {
        toast.warning(toastMessage, { duration: 8000 });
      });

      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('rate_limit_updated'));
      }
    }
    return done(ctx);
  }

  if (data.type === 'rate_limit_throttled') {
    const payload = data.data as { wait_seconds: number };
    if (payload) {
      const waitSec = Math.round(payload.wait_seconds);
      const lang = typeof document !== 'undefined' ? document.documentElement.lang : 'en';
      const toastMessage = lang?.startsWith('zh')
        ? `所有 API 配额已耗尽，正在等待恢复（约 ${waitSec} 秒）...`
        : `All API quotas exhausted, waiting for recovery (~${waitSec}s)...`;

      import('@/lib/utils/toast').then(({ toast }) => {
        toast.info(toastMessage, { duration: Math.min(waitSec * 1000, 30000) });
      });
    }
    return done(ctx);
  }

  return null;
}
