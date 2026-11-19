/**
 * [INPUT]
 * - @/components/dev/e2eBridge/hostEnv::resolveE2eApiBase (POS: 开发桥的页面环境探针)
 *
 * [OUTPUT]
 * - SEND_TURN_REV: revision tag echoed in send diagnostics and in `window.__MYRM_E2E_SEND_TURN_REV__`
 * - SEND_TURN_OBSERVE_MS / SEND_TURN_API_POLL_TIMEOUT_MS: observation window and per-poll cap, equal to the `dev_gate.contract` constants (pinned by tests)
 * - resolveSendTurnNoOpMs(): the no-progress budget of the current page
 *
 * [POS]
 * 发送回合中与 Python 端 dev_gate 契约逐值对应的常量：修订标记、封口观察窗口、消息列表轮询上限与无进展预算。
 */
import { resolveE2eApiBase } from '@/components/dev/e2eBridge/hostEnv';

export const SEND_TURN_REV = 'R72-K';

const SEND_TURN_NO_OP_MS = 3_000;

/**
 * No-progress budget of a page bound to an injected E2E backend. The first send of a page waits for the dev
 * server to serve the lazily loaded send pipeline (about 15 s while it is cold), and persisting the user row and
 * arming SSE can exceed 3 s under parallel load. The budget has to outlast both, or a healthy send is reported
 * as dead.
 */
const SEND_TURN_NO_OP_INJECTED_MS = 45_000;

/**
 * How long a new chat may take to commit its first assistant output, which persists the user
 * row. Must equal SEND_TURN_OBSERVE_SEC in scripts/dev/lib/dev_gate/contract/wall_clock.py (a test pins it).
 */
export const SEND_TURN_OBSERVE_MS = 90_000;

/**
 * Cap on one message-list poll. Must equal SEND_TURN_API_POLL_TIMEOUT_SEC in
 * scripts/dev/lib/dev_gate/contract/wall_clock.py (a test pins it). Without it a poll that never answers
 * holds the observe loop until the Python wall ends the send as an unclassified timeout.
 */
export const SEND_TURN_API_POLL_TIMEOUT_MS = 10_000;

export function resolveSendTurnNoOpMs(): number {
  if (typeof window === 'undefined') {
    return SEND_TURN_NO_OP_MS;
  }
  if (resolveE2eApiBase()) {
    return SEND_TURN_NO_OP_INJECTED_MS;
  }
  return SEND_TURN_NO_OP_MS;
}
