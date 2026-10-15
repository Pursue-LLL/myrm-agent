/**
 * stall-probe — what the pages behind a stalled request answer right now.
 *
 * [INPUT]:  the proxy's pending-request map; router lookups (the page a session belongs to, the shared
 *           session attached to a page, its url); a hook that evaluates an expression on a session and
 *           times out; the renderer snapshot (process-snapshot.mjs); a log sink.
 * [OUTPUT]: `forensics()` — logs one `stall page <id> [<url>] …` line per page that has a stalled request
 *           and resolves with the renderer snapshot line, which request-watch logs as `stall snapshot …`.
 *           A page line says how long a trivial read-only `evaluate` took to be answered (or that it
 *           stayed unanswered), plus readyState, visibilityState and the navigation timing, so a stall
 *           can be told apart: an unanswered probe on a renderer that runs flat out (core share ~1 in the
 *           snapshot) is a page that is busy; an unanswered probe on a runnable renderer with a low core
 *           share is one the host does not schedule; an answered probe on a loaded page says the stall
 *           was not in that page.
 * [POS]:    request-watch's `stallSnapshot` hook. It runs once per burst of stalls and only reads: it
 *           never creates a session (an unowned attach event would be broadcast to every client) and
 *           never closes anything (that is hang-guard's decision).
 */

import { snapshotRenderers } from './process-snapshot.mjs';

const PROBE_TIMEOUT_MS = 3000;
const MAX_PAGES = 3;
const SLOW_MS = 10_000;
// Navigation timing is read from the page itself: [readyState, visibilityState, [ttfb, dcl, load] | null].
export const PROBE_EXPRESSION = 'JSON.stringify((() => { const n = performance.getEntriesByType("navigation")[0]; '
    + 'return [document.readyState, document.visibilityState, '
    + 'n ? [n.responseStart, n.domContentLoadedEventEnd, n.loadEventEnd].map(Math.round) : null]; })())';

/** What an answered probe says about the page; a 0 timing means that milestone has not happened yet. */
function describeAnswer(response) {
    if (response?.error) return `answered with an error (${String(response.error.message).slice(0, 80)}), so its process is alive`;
    try {
        const [ready, visibility, nav] = JSON.parse(response.result.result.value);
        const milestones = nav ? nav.map((ms) => (ms > 0 ? ms : 'pending')).join('/') : 'unavailable';
        return `ready=${ready} visibility=${visibility} navigation ttfb/dcl/load=${milestones}ms`;
    } catch (_) {
        return 'returned a result that could not be read';
    }
}

/**
 * @param {object} hooks
 * @param {Map<number, { client: object | null, sessionId?: string, awaitsScript?: boolean, createdAt: number }>} hooks.pendingRequests
 * @param {(sessionId: string) => string | null} hooks.pageOfSession
 * @param {(targetId: string) => string | undefined} hooks.baseSessionOfPage
 * @param {(targetId: string) => string} hooks.describePage  current url of the page, for the log
 * @param {(sessionId: string, expression: string, timeoutMs: number) => Promise<object>} hooks.probe  rejects with `timedOut` when unanswered
 * @param {() => Promise<string | null>} hooks.renderers
 * @param {(line: string) => void} hooks.log
 */
export function createStallForensics({
    pendingRequests, pageOfSession, baseSessionOfPage, describePage, probe, renderers, log,
    slowMs = SLOW_MS, now = Date.now, clock = Date.now,
}) {
    /** Pages (at most MAX_PAGES) that hold a client request Chrome has left unanswered; script waits are not stalls. */
    function stalledPages() {
        const t = now();
        const pages = new Set();
        for (const req of pendingRequests.values()) {
            if (!req.client || !req.sessionId || req.awaitsScript || t - req.createdAt < slowMs) continue;
            const page = pageOfSession(req.sessionId);
            if (page) pages.add(page);
            if (pages.size >= MAX_PAGES) break;
        }
        return [...pages];
    }

    async function probeOutcome(page) {
        const session = baseSessionOfPage(page);
        if (!session) return 'cannot be probed (no shared session is attached to it)';
        const startedAt = clock();
        try {
            const response = await probe(session, PROBE_EXPRESSION, PROBE_TIMEOUT_MS);
            return `a trivial evaluate was answered in ${clock() - startedAt}ms: ${describeAnswer(response)}`;
        } catch (err) {
            return err?.timedOut ? `a trivial evaluate got no answer within ${PROBE_TIMEOUT_MS}ms` : `could not be probed (${err?.message})`;
        }
    }

    async function probePage(page) {
        let url = '';
        try { url = describePage(page).slice(0, 80); } catch (_) { /* a page that is gone has no url */ }
        log(`stall page ${page.slice(0, 8)} [${url}] ${await probeOutcome(page)}`);
    }

    /** Never rejects: forensics must not be able to disturb the proxy. */
    return async function forensics() {
        const [line] = await Promise.all([
            Promise.resolve().then(renderers).catch(() => null),
            ...stalledPages().map((page) => probePage(page).catch(() => {})),
        ]);
        return line;
    };
}

/** The hook for the real proxy: its router, its own CDP channel (internal requests time out by themselves) and Chrome's pid. */
export function createProxyStallForensics({ pendingRequests, router, cdpRequest, chromePid, log }) {
    return createStallForensics({
        pendingRequests,
        log,
        pageOfSession: (sessionId) => router.pageOfSession(sessionId),
        baseSessionOfPage: (targetId) => router.baseSessionOfPage(targetId),
        describePage: (targetId) => router.knownTargets.get(targetId)?.url ?? '',
        probe: (sessionId, expression, timeoutMs) => cdpRequest('Runtime.evaluate', { expression, returnByValue: true }, { sessionId, timeoutMs }),
        renderers: () => snapshotRenderers(chromePid()),
    });
}
