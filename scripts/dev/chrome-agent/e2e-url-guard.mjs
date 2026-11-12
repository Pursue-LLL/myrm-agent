/**
 * e2e-url-guard — keeps ChromeAgent :9410 for Agent tasks (e.g. URL extraction): navigating it to a
 * localhost UI that belongs to ChromeE2E :9333 is refused, over the WebSocket (`Page.navigate`,
 * `Target.createTarget`) and over the HTTP open route alike.
 *
 * Pure policy, no I/O: the proxy decides what to log and how to answer. `allow` lifts the guard
 * (MYRM_CHROME_AGENT_ALLOW_E2E_URLS=1).
 *
 * The shared dev UI port comes from `./dev-ports.mjs`, a symlink to the port SSOT in `../lib/`. The
 * machine-level installer copies only this directory's top-level modules (and follows the link),
 * so the bundle stays self-contained and never imports from a checkout.
 */

import { SHARED_FRONTEND_PORT } from './dev-ports.mjs';

export const E2E_URL_REJECT_CODE = -32001;
export const E2E_URL_REJECT_MESSAGE =
    'CHROME_AGENT_E2E_URL_REJECTED: ChromeAgent :9410 is for Agent tasks (e.g. URL extraction) only; '
    + 'chrome_e2e must use ./myrm-dev test harness → ChromeE2E :9333';

/** Product UI (3000), the website (3002) and the shared dev UI: all belong on ChromeE2E. */
const E2E_UI_PORTS = new Set(['3000', '3002', String(SHARED_FRONTEND_PORT)]);
const NAVIGATING_METHODS = new Set(['Page.navigate', 'Target.createTarget']);

/**
 * @param {object} options
 * @param {boolean} options.allow  lift the guard
 */
export function createE2eUrlGuard({ allow }) {
    /** True for a localhost UI URL that belongs on ChromeE2E. */
    function isForbidden(rawUrl) {
        if (allow || typeof rawUrl !== 'string' || !rawUrl.trim()) return false;
        let parsed;
        try {
            parsed = new URL(rawUrl);
        } catch {
            return false;
        }
        const host = parsed.hostname.toLowerCase();
        if (host !== '127.0.0.1' && host !== 'localhost') return false;
        const port = parsed.port || (parsed.protocol === 'https:' ? '443' : '80');
        return E2E_UI_PORTS.has(port);
    }

    return {
        isForbidden,

        /** The forbidden URL a client's CDP request navigates to, or undefined when the request may pass. */
        forbiddenNavigation(msg) {
            if (!NAVIGATING_METHODS.has(msg.method)) return undefined;
            const url = msg.params?.url;
            return isForbidden(url) ? url : undefined;
        },

        /** The CDP error reply to the request `id` that was refused. */
        rejection(id) {
            return { id, error: { code: E2E_URL_REJECT_CODE, message: E2E_URL_REJECT_MESSAGE } };
        },
    };
}
