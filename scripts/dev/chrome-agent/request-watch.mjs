/**
 * request-watch — makes a stalled Chrome visible while it is happening.
 *
 * A CDP request that Chrome does not answer sits in the proxy's pending map until the
 * 60 s reaper replies "CDP request timeout (60s)". To the session that is a page that
 * "hung"; nothing in the proxy log said which request, from which connection, or how
 * loaded the machine was at that moment. This module only observes the pending map (it
 * is not on the request path): a client request still unanswered after `slowMs` is logged
 * once with its method, connection, session and the host's load average, and a later line
 * says when it left the pending set. `stats()` feeds `/proxy/status`.
 */
import os from 'node:os';

const SLOW_MS = 10_000;
const TICK_MS = 2000;

export class RequestWatch {
    /**
     * @param {object} hooks
     * @param {Map<number, { client: { label: string } | null, method: string, sessionId?: string, createdAt: number }>} hooks.pendingRequests
     * @param {(line: string) => void} hooks.log
     * @param {number} [hooks.slowMs]
     * @param {() => number} [hooks.now]
     * @param {() => number[]} [hooks.loadavg]
     * @param {number} [hooks.cpus]
     */
    constructor({ pendingRequests, log, slowMs = SLOW_MS, now = Date.now, loadavg = os.loadavg, cpus = os.availableParallelism() }) {
        this.pendingRequests = pendingRequests;
        this.log = log;
        this.slowMs = slowMs;
        this.now = now;
        this.loadavg = loadavg;
        this.cpus = cpus;
        /** proxyId → what was logged for it and when it was last seen pending, until it leaves the map */
        this.flagged = new Map();
        this.slowCount = 0;
    }

    sweep() {
        const t = this.now();
        for (const [proxyId, req] of this.pendingRequests) {
            // Proxy-internal requests (no client) carry their own 5 s timeout.
            if (!req.client) continue;
            const known = this.flagged.get(proxyId);
            if (known) known.lastSeen = t;
            if (known || t - req.createdAt < this.slowMs) continue;
            const info = { label: req.client.label, method: req.method, createdAt: req.createdAt, lastSeen: t };
            this.flagged.set(proxyId, info);
            this.slowCount++;
            const session = req.sessionId ? ` sess=${req.sessionId.slice(0, 8)}` : '';
            this.log(`slow request ${info.label} ${info.method}${session} unanswered for ${this.#seconds(t - req.createdAt)}s `
                + `(load ${this.loadavg()[0].toFixed(0)} on ${this.cpus} cpus, ${this.pendingRequests.size} pending)`);
        }
        for (const [proxyId, info] of this.flagged) {
            if (this.pendingRequests.get(proxyId)?.createdAt === info.createdAt) continue;
            this.flagged.delete(proxyId);
            this.log(`slow request ${info.label} ${info.method} left the pending set after at least ${this.#seconds(info.lastSeen - info.createdAt)}s `
                + '(answered, or timed out by the 60 s reaper)');
        }
    }

    stats() {
        return { slowRequests: this.slowCount, loadavg1: Number(this.loadavg()[0].toFixed(1)), cpus: this.cpus };
    }

    #seconds(ms) {
        return Math.round(ms / 1000);
    }
}

/** Create the watch and sweep it while the proxy runs. */
export function startRequestWatch({ pendingRequests, log }) {
    const watch = new RequestWatch({ pendingRequests, log });
    setInterval(() => watch.sweep(), TICK_MS).unref();
    return watch;
}
