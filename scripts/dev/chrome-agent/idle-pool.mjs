/**
 * idle-pool — keeps a floor of idle (`about:blank`, unleased) tabs in the shared Chrome.
 *
 * Sessions are told never to open tabs themselves, so the number of tasks that can run
 * at once equals the number of idle tabs. Nothing else maintains that number: a fresh or
 * restarted Chrome starts with a single tab, and every claimed tab removes one from the
 * pool. The proxy therefore tops the pool up (in the background, no focus change) whenever
 * fewer than `minIdle` idle tabs remain, up to `maxPages` tabs in total.
 *
 * Every pooled tab gets a window of its own. A window shows one tab and Chrome hides the
 * rest; a hidden tab's renderer is starved under load (CDP calls time out for tens of
 * seconds and heavy pages such as x.com never finish rendering), and the sessions never
 * bring their tab to the front. A tab that shares its window with other tabs is therefore
 * not idle. The pool never creates such a tab, so a blank shared-window tab was opened by
 * someone else (a client with an explicit `newWindow:false`, a popup) and may be in use
 * right now: it is closed only after it has stayed blank and unleased for `abandonGraceMs`.
 *
 * The only other tabs closed here are those whose session disconnected without releasing
 * them (tab-lease `abandoned`), after the same grace, so leaked tabs cannot eat the cap.
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
     * @param {() => number} [hooks.now]
     */
    constructor({ cdpRequest, isLeased, log, minIdle, maxPages, takeAbandoned, abandonGraceMs, now = Date.now }) {
        this.now = now;
        this.cdpRequest = cdpRequest;
        this.isLeased = isLeased;
        this.log = log;
        this.minIdle = minIdle;
        this.maxPages = maxPages;
        this.takeAbandoned = takeAbandoned;
        this.abandonGraceMs = abandonGraceMs;
        this.running = false;
        /** targetId → id of the window holding it (a tab never changes window) */
        this.windowIds = new Map();
        /** targetId → when it was first seen as a blank, unleased tab in a shared window, while it stays one */
        this.sharedBlankSince = new Map();
        /** Pages beyond the first in their window (hidden tabs) at the last reconcile; null before the first. */
        this.sharedWindowPages = null;
    }

    /** Merged into /proxy/status. */
    stats() {
        return { sharedWindowPages: this.sharedWindowPages };
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
            const { windowOf, population } = await this.#windowPopulation(pages);
            this.sharedWindowPages = pages.length - population.size;
            // An empty url is a tab Chrome has just created and not yet reported as blank.
            const blank = pages.filter((t) => (t.url === BLANK || t.url === '') && !this.isLeased(t.targetId));
            const idle = blank.filter((t) => population.get(windowOf.get(t.targetId)) === 1);
            const shared = blank.filter((t) => !idle.includes(t));
            const needed = Math.max(0, this.minIdle - idle.length);
            let room = this.maxPages - pages.length;
            const unused = this.#unusedSharedBlanks(shared);
            await this.#closeTabs(unused, 'unused shared-window blank tab');
            room += unused.length;
            const missing = Math.min(needed, room);
            for (let i = 0; i < missing; i++) {
                const created = await this.cdpRequest('Target.createTarget', { url: BLANK, newWindow: true, background: true });
                if (created.error) throw new Error(created.error.message);
            }
            if (missing > 0) {
                this.log(`idle pool: ${idle.length} idle of ${pages.length} tabs, opened ${missing} (floor ${this.minIdle}, cap ${this.maxPages})`);
            }
        } catch (err) {
            // Chrome restarting or briefly unresponsive; the next tick retries.
            this.log(`idle pool: reconcile skipped (${err.message})`);
        } finally {
            this.running = false;
        }
    }

    /** Window of every page and page count per window; a tab whose window cannot be resolved counts as alone in it. */
    async #windowPopulation(pages) {
        const live = new Set(pages.map((t) => t.targetId));
        for (const id of this.windowIds.keys()) if (!live.has(id)) this.windowIds.delete(id);
        const windowOf = new Map();
        const population = new Map();
        for (const tab of pages) {
            let windowId = this.windowIds.get(tab.targetId);
            if (windowId === undefined) {
                const { result } = await this.cdpRequest('Browser.getWindowForTarget', { targetId: tab.targetId });
                if (result?.windowId !== undefined) this.windowIds.set(tab.targetId, result.windowId);
                windowId = result?.windowId ?? `unresolved:${tab.targetId}`;
            }
            windowOf.set(tab.targetId, windowId);
            population.set(windowId, (population.get(windowId) ?? 0) + 1);
        }
        return { windowOf, population };
    }

    /** Shared-window blank tabs that have been blank and unleased for the whole grace period. */
    #unusedSharedBlanks(shared) {
        const t = this.now();
        const current = new Set(shared.map((tab) => tab.targetId));
        for (const id of this.sharedBlankSince.keys()) if (!current.has(id)) this.sharedBlankSince.delete(id);
        for (const id of current) if (!this.sharedBlankSince.has(id)) this.sharedBlankSince.set(id, t);
        return shared.filter((tab) => t - this.sharedBlankSince.get(tab.targetId) >= this.abandonGraceMs);
    }

    async #closeTabs(tabs, what) {
        for (const tab of tabs) {
            const closed = await this.cdpRequest('Target.closeTarget', { targetId: tab.targetId });
            if (closed.error) throw new Error(closed.error.message);
            this.log(`idle pool: closed ${what} ${tab.targetId.slice(0, 8)} (${tab.url.slice(0, 80)})`);
        }
    }

    /** Close tabs whose lessee left them on a page; returns the pages that remain. */
    async #closeAbandoned(pages) {
        const expired = new Set(this.takeAbandoned(this.abandonGraceMs));
        // Re-check against Chrome's current view: the tab may have been released or claimed since.
        const doomed = pages.filter((t) => expired.has(t.targetId) && t.url !== BLANK && !this.isLeased(t.targetId));
        await this.#closeTabs(doomed, 'abandoned tab');
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
