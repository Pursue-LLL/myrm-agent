/**
 * context-replay — execution contexts for late joiners of a shared base session.
 *
 * Chrome announces a page's execution contexts only to the Runtime.enable that actually
 * turns the domain on; a second Runtime.enable on the same session is a no-op. Base
 * sessions are shared, so a client that attaches after another client enabled Runtime
 * never learns the contexts, and every evaluate on a page it has not navigated itself
 * waits for a context that is never announced. The proxy sees every context event, so it
 * replays the live set to a client whose Runtime.enable lands on an already-enabled
 * session — the same way the router replays targets and sessions to late clients.
 */

const ENABLE = 'Runtime.enable';
const DISABLE = 'Runtime.disable';
const CREATED = 'Runtime.executionContextCreated';
const DESTROYED = 'Runtime.executionContextDestroyed';
const CLEARED = 'Runtime.executionContextsCleared';

export class ContextReplay {
    constructor() {
        /** sessionId → Map<contextId, executionContextCreated params> for the contexts Chrome announced */
        this.contexts = new Map();
        /** sessions whose Runtime domain Chrome has turned on (proved by a completed enable or a context event) */
        this.enabled = new Set();
        /** proxyId → { client, sessionId, method, late } for in-flight Runtime.enable / Runtime.disable */
        this.pending = new Map();
    }

    /**
     * Remember a Runtime.enable / Runtime.disable that is about to be forwarded under `proxyId`.
     * Whether the enable is "late" is decided now: a first enable's own events must not be echoed back.
     */
    track(proxyId, client, msg) {
        if (!msg.sessionId || (msg.method !== ENABLE && msg.method !== DISABLE)) return;
        this.pending.set(proxyId, {
            client,
            sessionId: msg.sessionId,
            method: msg.method,
            late: this.enabled.has(msg.sessionId),
        });
    }

    abandon(proxyId) {
        this.pending.delete(proxyId);
    }

    /** The proxy drops a closed client's in-flight requests, so their answers never reach `settle`. */
    dropClient(client) {
        for (const [proxyId, request] of this.pending) {
            if (request.client === client) this.pending.delete(proxyId);
        }
    }

    /**
     * Apply Chrome's answer. Returns the events to deliver to the requesting client before
     * the response (a late Runtime.enable), or null when there is nothing to replay.
     */
    settle(proxyId, response) {
        const request = this.pending.get(proxyId);
        if (!request) return null;
        this.pending.delete(proxyId);
        if (response.error) return null;

        const { client, sessionId, method, late } = request;
        if (method === DISABLE) {
            this.forget(sessionId);
            return null;
        }
        this.enabled.add(sessionId);
        if (!late) return null;
        const events = [...(this.contexts.get(sessionId)?.values() ?? [])]
            .map((params) => ({ method: CREATED, params, sessionId }));
        return events.length ? { client, events } : null;
    }

    /** Track the live contexts of a base session from the events Chrome sends. */
    observe({ method, params, sessionId }) {
        if (!sessionId) return;
        if (method === CREATED && params?.context) {
            this.enabled.add(sessionId);
            let live = this.contexts.get(sessionId);
            if (!live) this.contexts.set(sessionId, (live = new Map()));
            live.set(params.context.id, params);
        } else if (method === DESTROYED) {
            this.contexts.get(sessionId)?.delete(params?.executionContextId);
        } else if (method === CLEARED) {
            this.contexts.delete(sessionId);
        }
    }

    forget(sessionId) {
        this.contexts.delete(sessionId);
        this.enabled.delete(sessionId);
    }

    reset() {
        this.contexts.clear();
        this.enabled.clear();
        this.pending.clear();
    }
}
