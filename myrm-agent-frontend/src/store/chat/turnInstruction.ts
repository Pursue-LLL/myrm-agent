/**
 * [INPUT]
 * - @/lib/api::fetchWithTimeout (POS: 前端 API 接入层，直连请求 SSOT)
 * - @/lib/mobileRemote::{isMobileRemoteSurface, mobileRemotePost} (POS: Mobile remote surface request channel)
 *
 * [OUTPUT]
 * - postTurnInstruction: deliver a steer / redirect instruction to the turn running in a chat and report whether that turn took it.
 *
 * [POS]
 * Transport of mid-turn instructions. The backend refuses an instruction ("no active agent for this chat") with HTTP 200
 * and a `success: false` envelope, so acceptance is read from the envelope, not the status. Callers rely on `false` to
 * keep the instruction (queue it, refill the composer) rather than treat it as delivered.
 */
import { fetchWithTimeout } from '@/lib/api';

export type TurnInstructionKind = 'steer' | 'redirect';

function isRefusal(body: unknown): boolean {
  return typeof body === 'object' && body !== null && (body as { success?: unknown }).success === false;
}

/**
 * Resolves true only when the running turn took the instruction. A refusal envelope, an HTTP error status, an unreadable
 * body and a failed request all resolve false: an instruction wrongly reported as refused is queued where the user can
 * see it, one wrongly reported as accepted is lost without a trace.
 */
export async function postTurnInstruction(
  chatId: string,
  kind: TurnInstructionKind,
  payload: Record<string, unknown>,
): Promise<boolean> {
  try {
    const { isMobileRemoteSurface, mobileRemotePost } = await import('@/lib/mobileRemote');
    if (isMobileRemoteSurface()) {
      return !isRefusal(await mobileRemotePost<unknown>(`/api/v1/agents/chats/${chatId}/${kind}`, payload));
    }
    const res = await fetchWithTimeout(`/agents/chats/${chatId}/${kind}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    return res.ok && !isRefusal(await res.json());
  } catch {
    return false;
  }
}
