/**
 * request-watch — makes a stalled Chrome visible while it is happening.
 *
 * A CDP request that Chrome does not answer sits in the proxy's pending map until the
 * 60 s reaper replies "CDP request timeout (60s)". To the session that is a page that
 * "hung"; nothing in the proxy log said which request, from which connection, or how
 * loaded the machine was at that moment. This module only observes the pending map (it
 * is not on the request path): a client request still unanswered after `slowMs` is logged
 * once with its method, connection, the target its session is attached to (page, iframe,
 * worker and its current url; "session unknown to the proxy" when the router no longer
 * knows it), the host's load average and how long Chrome has been up, and a later line
 * says when it left the pending set. The first stall of a burst also logs a snapshot of
 * Chrome's renderer processes (priority, CPU share). `stats()` feeds `/proxy/status`
 * (slow requests, those on unknown sessions, load, cpus).
 */
import os from 'node:os';

const SLOW_MS = 10_000;
const TICK_MS = 2000;
/** One process snapshot per burst of stalls: a stalled Chrome often stalls dozens of requests at once. */
const SNAPSHOT_COOLDOWN_MS = 30_000;

export class RequestWatch {
    /**
     * @param {object} hooks
     * @param {Map<number, { client: { label: string } | null, method: string, sessionId?: string, createdAt: number }>} hooks.pendingRequests
     * @param {(line: string) => void} hooks.log
     * @param {number} [hooks.slowMs]
     * @param {() => number} [hooks.now]
     * @param {() => number[]} [hooks.loadavg]
     * @param {number} [hooks.cpus]
     * @param {() => number | null} [hooks.chromeAgeMs]  how long the current Chrome has been up, null when it is not running
     * @param {(sessionId: string) => string | null} [hooks.describeSession]  what a session is attached to (page, iframe, worker …)
     * @param {() => Promise<string | null>} [hooks.stallSnapshot]  describes Chrome's renderer processes right now
     */
    constructor({ pendingRequests, log, slowMs = SLOW_MS, now = Date.now, loadavg = os.loadavg, cpus = os.availableParallelism(), chromeAgeMs = () => null, describeSession = () => null, stallSnapshot = async () => null }) {
        this.chromeAgeMs = chromeAgeMs;
        this.stallSnapshot = stallSnapshot;
        this.lastSnapshotAt = -Infinity;
        this.describeSession = describeSession;
        this.pendingRequests = pendingRequests;
        this.log = log;
        this.slowMs = slowMs;
        this.now = now;
        this.loadavg = loadavg;
        this.cpus = cpus;
        /** proxyId → what was logged for it and when it was last seen pending, until it leaves the map */
        this.flagged = new Map();
        this.slowCount = 0;
        /** slow requests whose session the router no longer knows: Chrome drops commands for a detached session */
        this.unknownSessionCount = 0;
    }

    sweep() {
        const t = this.now();
        let newStall = false;
        for (const [proxyId, req] of this.pendingRequests) {
            // Proxy-internal requests (no client) carry their own 5 s timeout.
            if (!req.client) continue;
            const known = this.flagged.get(proxyId);
            if (known) known.lastSeen = t;
            if (known || t - req.createdAt < this.slowMs) continue;
            const info = { label: req.client.label, method: req.method, createdAt: req.createdAt, lastSeen: t };
            this.flagged.set(proxyId, info);
            this.slowCount++;
            newStall = true;
            const target = req.sessionId ? this.describeSession(req.sessionId) : null;
            const unknown = Boolean(req.sessionId) && !target;
            if (unknown) this.unknownSessionCount++;
            const session = req.sessionId ? ` sess=${req.sessionId.slice(0, 8)} [${target ?? 'session unknown to the proxy'}]` : '';
            const age = this.chromeAgeMs();
            const chrome = age === null ? '' : `, chrome up ${Math.round(age / 60_000)}m`;
            this.log(`slow request ${info.label} ${info.method}${session} unanswered for ${this.#seconds(t - req.createdAt)}s `
                + `(load ${this.loadavg()[0].toFixed(0)} on ${this.cpus} cpus, ${this.pendingRequests.size} pending${chrome})`);
        }
        if (newStall && t - this.lastSnapshotAt >= SNAPSHOT_COOLDOWN_MS) {
            this.lastSnapshotAt = t;
            this.stallSnapshot().then((line) => { if (line) this.log(`stall snapshot ${line}`); }, () => {});
        }
        for (const [proxyId, info] of this.flagged) {
            if (this.pendingRequests.get(proxyId)?.createdAt === info.createdAt) continue;
            this.flagged.delete(proxyId);
            this.log(`slow request ${info.label} ${info.method} left the pending set after at least ${this.#seconds(info.lastSeen - info.createdAt)}s `
                + '(answered, or timed out by the 60 s reaper)');
        }
    }

    stats() {
        return { slowRequests: this.slowCount, slowRequestsOnUnknownSession: this.unknownSessionCount, loadavg1: Number(this.loadavg()[0].toFixed(1)), cpus: this.cpus };
    }

    #seconds(ms) {
        return Math.round(ms / 1000);
    }
}

/** Create the watch and sweep it while the proxy runs. */
export function startRequestWatch({ pendingRequests, log, chromeAgeMs, describeSession, stallSnapshot }) {
    const watch = new RequestWatch({ pendingRequests, log, chromeAgeMs, describeSession, stallSnapshot });
    setInterval(() => watch.sweep(), TICK_MS).unref();
    return watch;
}
