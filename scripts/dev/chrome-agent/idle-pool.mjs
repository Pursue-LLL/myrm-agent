/**
 * idle-pool — keeps a floor of idle (`about:blank`, unleased) tabs in the shared Chrome.
 *
 * Sessions are told never to open tabs themselves, so the number of tasks that can run
 * at once equals the number of idle tabs. Nothing else maintains that number: a fresh or
 * restarted Chrome starts with a single tab, and every claimed tab removes one from the
 * pool. The proxy therefore tops the pool up (in the background, no focus change) whenever
 * fewer than `minIdle` idle tabs remain, up to `maxPages` tabs in total. Tabs are never
 * closed here, with one exception: a tab whose session disconnected without releasing it
 * (tab-lease `abandoned`) is closed after `abandonGraceMs`, so leaked tabs cannot eat the cap.
 * Any other non-idle tab may belong to a running task or to the user.
 */

const BLANK = 'about:blank';

export class IdlePool {
    /**
     * @param {object} hooks
     * @param {(method: string, params?: object) => Promise<{ result?: object, error?: object }>} hooks.cdpRequest
     * @param {(targetId: string) => boolean} hooks.isLeased
     * @param {(line: string) => void} hooks.log
     * @param {number} hooks.minIdle   idle tabs to keep available
     * @param {number} hooks.maxPages  hard cap on page targets
     * @param {(graceMs: number) => string[]} hooks.takeAbandoned  tabs left behind for at least graceMs
     * @param {number} hooks.abandonGraceMs
     */
    constructor({ cdpRequest, isLeased, log, minIdle, maxPages, takeAbandoned, abandonGraceMs }) {
        this.cdpRequest = cdpRequest;
        this.isLeased = isLeased;
        this.log = log;
        this.minIdle = minIdle;
        this.maxPages = maxPages;
        this.takeAbandoned = takeAbandoned;
        this.abandonGraceMs = abandonGraceMs;
        this.running = false;
    }

    /** Top the pool up if needed. Safe to call at any time; overlapping calls are dropped. */
    async reconcile() {
        if (this.running || this.minIdle <= 0) return;
        this.running = true;
        try {
            const { result, error } = await this.cdpRequest('Target.getTargets');
            if (error || !result?.targetInfos) return;
            let pages = result.targetInfos.filter((t) => t.type === 'page');
            pages = await this.#closeAbandoned(pages);
            // An empty url is a tab Chrome has just created and not yet reported as blank.
            const idle = pages.filter((t) => (t.url === BLANK || t.url === '') && !this.isLeased(t.targetId)).length;
            const missing = Math.min(this.minIdle - idle, this.maxPages - pages.length);
            for (let i = 0; i < missing; i++) {
                const created = await this.cdpRequest('Target.createTarget', { url: BLANK, background: true });
                if (created.error) throw new Error(created.error.message);
            }
            if (missing > 0) {
                this.log(`idle pool: ${idle} idle of ${pages.length} tabs, opened ${missing} (floor ${this.minIdle}, cap ${this.maxPages})`);
            }
        } catch (err) {
            // Chrome restarting or briefly unresponsive; the next tick retries.
            this.log(`idle pool: reconcile skipped (${err.message})`);
        } finally {
            this.running = false;
        }
    }

    /** Close tabs whose lessee left them on a page; returns the pages that remain. */
    async #closeAbandoned(pages) {
        const expired = new Set(this.takeAbandoned(this.abandonGraceMs));
        // Re-check against Chrome's current view: the tab may have been released or claimed since.
        const doomed = pages.filter((t) => expired.has(t.targetId) && t.url !== BLANK && !this.isLeased(t.targetId));
        for (const tab of doomed) {
            const closed = await this.cdpRequest('Target.closeTarget', { targetId: tab.targetId });
            if (closed.error) throw new Error(closed.error.message);
            this.log(`idle pool: closed abandoned tab ${tab.targetId.slice(0, 8)} (${tab.url.slice(0, 80)})`);
        }
        return pages.filter((t) => !doomed.includes(t));
    }
}

const TICK_MS = 2000;
const DEFAULT_MIN_IDLE = 3;
const DEFAULT_MAX_PAGES = 12;
const DEFAULT_ABANDON_GRACE_MS = 10 * 60_000;

/**
 * Create the pool and keep it reconciled while Chrome is up.
 * `CHROME_AGENT_MIN_IDLE_TABS` (0 disables), `CHROME_AGENT_MAX_PAGES` and
 * `CHROME_AGENT_ABANDON_GRACE_MS` override the defaults. `lease` is the proxy's TabLease.
 */
export function startIdlePool({ cdpRequest, lease, log, chromeUp, env = process.env }) {
    const pool = new IdlePool({
        cdpRequest,
        log,
        isLeased: (targetId) => lease.leases.has(targetId),
        takeAbandoned: (graceMs) => lease.takeAbandoned(graceMs),
        minIdle: Number(env.CHROME_AGENT_MIN_IDLE_TABS ?? DEFAULT_MIN_IDLE),
        maxPages: Number(env.CHROME_AGENT_MAX_PAGES ?? DEFAULT_MAX_PAGES),
        abandonGraceMs: Number(env.CHROME_AGENT_ABANDON_GRACE_MS ?? DEFAULT_ABANDON_GRACE_MS),
    });
    setInterval(() => { if (chromeUp()) pool.reconcile(); }, TICK_MS).unref();
    return pool;
}
