/**
 * hang-guard — bounds how long a page that stopped answering can hold a session.
 *
 * A CDP request Chrome never answers sits in the proxy's pending map. The proxy used to
 * reply "CDP request timeout (60s)" to it and do nothing else, so a session kept
 * retrying (evaluate, reload, evaluate …) on a page whose renderer would never answer
 * again: the 651 s "提取热帖" stall. On every sweep this module
 *
 *   1. replies the timeout to requests older than `maxAgeMs` (the reaper), and
 *   2. checks the page behind each of them: one trivial `Runtime.evaluate` goes through the
 *      proxy's own base session of that page. Answered (a result or an error) means the page
 *      is slow, not hung (e.g. waiting on a long network call): nothing is done. Silent for
 *      `probeMs`, and again for a second short probe sent right before closing (the page may
 *      have been released or replaced meanwhile), means the renderer is hung: the page is
 *      closed with `Target.closeTarget`
 *      (the browser process handles it, so it works on a hung renderer and frees its CPU),
 *      its other pending requests fail at once with PAGE_HUNG, and the tab lease and pool
 *      see an ordinary tab closure.
 *
 * Never creates a session of its own (an unowned attach event would be broadcast to every
 * client). More than `maxCloses` closures within `closeWindowMs` means Chrome or the host
 * stalls as a whole; the guard then only logs, since closing every page would destroy work
 * that resumes. Counters feed `/proxy/status`.
 *
 * Env overrides: `CHROME_AGENT_HANG_REQUEST_MS` (60000), `CHROME_AGENT_HANG_PROBE_MS`
 * (30000), `CHROME_AGENT_HANG_SWEEP_MS` (30000).
 */
import os from 'node:os';

const DEFAULT_REQUEST_MS = 60_000;
const DEFAULT_PROBE_MS = 30_000;
const DEFAULT_SWEEP_MS = 30_000;
/** Second, shorter probe right before closing (see #probeAndClose). */
const CONFIRM_MS = 3_000;
/** A page that answered its probe, or could not be probed or closed, is left alone for this long. */
const RECHECK_MS = 60_000;
const MAX_CLOSES = 3;
const CLOSE_WINDOW_MS = 10 * 60_000;

export class HangGuard {
    /**
     * @param {object} hooks
     * @param {Map<number, { clientWs: object, client: object | null, originalId: number, method: string, sessionId?: string, createdAt: number }>} hooks.pendingRequests
     * @param {(req: object, message: string) => void} hooks.reply  send an error to the request's client
     * @param {(proxyId: number, req: object) => void} hooks.abandon  client/router bookkeeping for a request that will never be answered
     * @param {(sessionId: string) => string | null} hooks.pageOfSession  the page target a session belongs to; null when unknown
     * @param {(targetId: string) => string | undefined} hooks.baseSessionOfPage  a shared session attached to the page itself
     * @param {(targetId: string) => string} hooks.describePage  current url of the page, for the log
     * @param {(sessionId: string, timeoutMs: number) => Promise<'alive' | 'silent' | 'unavailable'>} hooks.probe
     * @param {(targetId: string) => Promise<void>} hooks.closePage  rejects when Chrome refuses
     * @param {(line: string) => void} hooks.log
     */
    constructor({
        pendingRequests, reply, abandon, pageOfSession, baseSessionOfPage, describePage, probe, closePage, log,
        now = Date.now, loadavg = os.loadavg, cpus = os.availableParallelism(), chromeAgeMs = () => null,
        maxAgeMs = DEFAULT_REQUEST_MS, probeMs = DEFAULT_PROBE_MS,
    }) {
        Object.assign(this, {
            pendingRequests, reply, abandon, pageOfSession, baseSessionOfPage, describePage, probe, closePage, log,
            now, loadavg, cpus, chromeAgeMs, maxAgeMs, probeMs,
        });
        /** targetId → when it may be checked again (Infinity while a probe is in flight) */
        this.checks = new Map();
        this.closedAt = [];
        this.closedCount = 0;
        this.aliveCount = 0;
    }

    /** Reply the timeout to requests Chrome never answered, then check their pages. Resolves when those checks are done. */
    sweep() {
        const t = this.now();
        for (const [targetId, until] of this.checks) if (until <= t) this.checks.delete(targetId);
        const suspects = new Map();
        for (const [proxyId, req] of this.pendingRequests) {
            if (t - req.createdAt <= this.maxAgeMs) continue;
            this.pendingRequests.delete(proxyId);
            this.reply(req, `CDP request timeout (${this.maxAgeMs / 1000}s)`);
            this.abandon(proxyId, req);
            // Proxy-internal requests (no client) and browser-level ones (no session) say nothing about a page.
            const page = req.client && req.sessionId ? this.pageOfSession(req.sessionId) : null;
            if (page && !this.checks.has(page) && !suspects.has(page)) suspects.set(page, req);
        }
        return Promise.all([...suspects].map(([page, req]) => this.#check(page, req)));
    }

    stats() {
        return { hungPagesClosed: this.closedCount, hangProbesAnswered: this.aliveCount };
    }

    /** A failing hook must neither escape the sweep nor leave the page locked out of future checks. */
    async #check(page, req) {
        try {
            await this.#probeAndClose(page, req);
        } catch (err) {
            this.checks.set(page, this.now() + RECHECK_MS);
            this.log(`hang guard: check of page ${page.slice(0, 8)} failed (${err.message})`);
        }
    }

    /** One probe; a hook that throws counts as a probe that could not run. */
    async #probe(session, timeoutMs) {
        try {
            return await this.probe(session, timeoutMs);
        } catch (_) {
            return 'unavailable';
        }
    }

    async #probeAndClose(page, req) {
        const where = `${page.slice(0, 8)} (${this.describePage(page).slice(0, 80)})`;
        const session = this.baseSessionOfPage(page);
        if (!session) {
            this.checks.set(page, this.now() + RECHECK_MS);
            this.log(`hang guard: page ${where} cannot be probed (no shared session attached to it); left alone`);
            return;
        }
        this.checks.set(page, Infinity);
        let verdict = await this.#probe(session, this.probeMs);
        // The page may have been released or replaced while it was probed (a navigation swaps the
        // renderer, so a blank tab would be closed under its next user): judge it again before closing.
        if (verdict === 'silent') verdict = await this.#probe(session, CONFIRM_MS);
        if (verdict !== 'silent') {
            this.checks.set(page, this.now() + RECHECK_MS);
            if (verdict === 'alive') {
                this.aliveCount++;
                this.log(`hang guard: page ${where} is slow, not hung (${req.method} from ${req.client.label} was reaped, a probe was answered)`);
            }
            return;
        }
        const recent = this.closedAt.filter((at) => this.now() - at < CLOSE_WINDOW_MS);
        if (recent.length >= MAX_CLOSES) {
            this.checks.set(page, this.now() + RECHECK_MS);
            this.log(`hang guard: page ${where} is hung but NOT closed: ${recent.length} pages were closed in the last ${CLOSE_WINDOW_MS / 60_000} min, `
                + 'which points at Chrome or the host rather than one page');
            return;
        }
        // Taken before the close: Chrome's detach events make the sessions unresolvable afterwards.
        const orphaned = [...this.pendingRequests].filter(([, r]) => r.client && r.sessionId && this.pageOfSession(r.sessionId) === page);
        try {
            await this.closePage(page);
        } catch (err) {
            this.checks.set(page, this.now() + RECHECK_MS);
            this.log(`hang guard: page ${where} is hung but could not be closed (${err.message})`);
            return;
        }
        this.checks.delete(page);
        this.closedAt = [...recent, this.now()];
        this.closedCount++;
        for (const [proxyId, r] of orphaned) {
            if (this.pendingRequests.get(proxyId) !== r) continue;
            this.pendingRequests.delete(proxyId);
            this.reply(r, `PAGE_HUNG: this page stopped answering (a trivial probe got no reply for ${this.probeMs / 1000}s), so the proxy closed it and freed its tab. `
                + 'Do not retry on it; report PAGE_STALL');
            this.abandon(proxyId, r);
        }
        const age = this.chromeAgeMs();
        this.log(`hang guard: closed hung page ${where}: ${req.method} from ${req.client.label} unanswered for ${Math.round((this.now() - req.createdAt) / 1000)}s `
            + `and neither the probe (${this.probeMs / 1000}s) nor a second one (${CONFIRM_MS / 1000}s) got a reply (load ${this.loadavg()[0].toFixed(0)} on ${this.cpus} cpus${age === null ? '' : `, chrome up ${Math.round(age / 60_000)}m`}); `
            + `${orphaned.length} other pending request(s) failed`);
    }
}

/** Create the guard from the proxy's pieces and sweep it while the proxy runs. */
export function startHangGuard({ pendingRequests, router, safeSend, cdpRequest, log, chromeAgeMs, env = process.env }) {
    const guard = new HangGuard({
        pendingRequests,
        log,
        chromeAgeMs,
        maxAgeMs: Number(env.CHROME_AGENT_HANG_REQUEST_MS ?? DEFAULT_REQUEST_MS),
        probeMs: Number(env.CHROME_AGENT_HANG_PROBE_MS ?? DEFAULT_PROBE_MS),
        reply: (req, message) => safeSend(req.clientWs, { id: req.originalId, error: { code: -32000, message } }),
        abandon: (proxyId, req) => {
            req.client?.proxyIds.delete(proxyId);
            router.onRequestAbandoned(proxyId);
        },
        pageOfSession: (sessionId) => router.pageOfSession(sessionId),
        baseSessionOfPage: (targetId) => router.baseSessionOfPage(targetId),
        describePage: (targetId) => router.knownTargets.get(targetId)?.url ?? '',
        // Any answer, a result or an error, proves the page's process is alive; only silence is a hang.
        probe: (sessionId, timeoutMs) => cdpRequest('Runtime.evaluate', { expression: '1' }, { sessionId, timeoutMs })
            .then(() => 'alive', (err) => (err.timedOut ? 'silent' : 'unavailable')),
        closePage: async (targetId) => {
            const { error } = await cdpRequest('Target.closeTarget', { targetId });
            if (error) throw new Error(error.message);
        },
    });
    setInterval(() => {
        guard.sweep();
        router.purgeOrphans();
    }, Number(env.CHROME_AGENT_HANG_SWEEP_MS ?? DEFAULT_SWEEP_MS)).unref();
    return guard;
}
