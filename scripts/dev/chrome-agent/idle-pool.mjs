/**
 * idle-pool — keeps a floor of idle (`about:blank`, unleased) tabs in the shared Chrome.
 *
 * Sessions are told never to open tabs themselves, so the number of tasks that can run
 * at once equals the number of idle tabs. Nothing else maintains that number: a fresh or
 * restarted Chrome starts with a single tab, and every claimed tab removes one from the
 * pool. The proxy therefore tops the pool up (in the background, no focus change) whenever
 * fewer than `minIdle` idle tabs remain, up to `maxPages` tabs in total. Tabs are never
 * closed here: a tab that is not idle may belong to a running task or to the user.
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
     */
    constructor({ cdpRequest, isLeased, log, minIdle, maxPages }) {
        this.cdpRequest = cdpRequest;
        this.isLeased = isLeased;
        this.log = log;
        this.minIdle = minIdle;
        this.maxPages = maxPages;
        this.running = false;
    }

    /** Top the pool up if needed. Safe to call at any time; overlapping calls are dropped. */
    async reconcile() {
        if (this.running || this.minIdle <= 0) return;
        this.running = true;
        try {
            const { result, error } = await this.cdpRequest('Target.getTargets');
            if (error || !result?.targetInfos) return;
            const pages = result.targetInfos.filter((t) => t.type === 'page');
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
}

const TICK_MS = 2000;
const DEFAULT_MIN_IDLE = 3;
const DEFAULT_MAX_PAGES = 12;

/**
 * Create the pool and keep it reconciled while Chrome is up.
 * `CHROME_AGENT_MIN_IDLE_TABS` (0 disables) and `CHROME_AGENT_MAX_PAGES` override the defaults.
 */
export function startIdlePool({ cdpRequest, isLeased, log, chromeUp, env = process.env }) {
    const pool = new IdlePool({
        cdpRequest,
        isLeased,
        log,
        minIdle: Number(env.CHROME_AGENT_MIN_IDLE_TABS ?? DEFAULT_MIN_IDLE),
        maxPages: Number(env.CHROME_AGENT_MAX_PAGES ?? DEFAULT_MAX_PAGES),
    });
    setInterval(() => { if (chromeUp()) pool.reconcile(); }, TICK_MS).unref();
    return pool;
}
