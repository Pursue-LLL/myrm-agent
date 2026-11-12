/**
 * browser-context-owners — ties every isolated browser context to the connection that created it.
 *
 * chrome-devtools-mcp opens one `Target.createBrowserContext` per `isolatedContext` name and never
 * disposes it. The browser behind this proxy outlives every client, so without an owner a context
 * (and the renderers of its pages) stays until Chrome restarts. Contexts are private to their
 * creator the way owned CDP sessions are (session-router.mjs): disposed when its connection goes away.
 *
 * Only contexts a client created through the proxy are ever disposed, and never while their creator
 * is connected: a client may reuse a context whose pages it closed.
 *
 * The creation request must outlive a client that disconnects while it is in flight (the proxy keeps
 * it pending, see `outlivesClient` in session-router.mjs): Chrome's answer is then the only place
 * the new context's id is known, and it is disposed on arrival.
 *
 * No I/O: the proxy injects the dispose callback.
 */

const CREATE = 'Target.createBrowserContext';
const DISPOSE = 'Target.disposeBrowserContext';

export const createsBrowserContext = (method) => method === CREATE;

export class BrowserContextOwners {
    /**
     * @param {object} hooks
     * @param {(browserContextId: string) => void} hooks.dispose  ask Chrome to dispose a context
     * @param {(line: string) => void} hooks.log
     */
    constructor({ dispose, log }) {
        this.dispose = dispose;
        this.log = log;
        /** browserContextId → the client that created it */
        this.owners = new Map();
        /** proxyId → client, for creation requests awaiting Chrome's answer */
        this.pendingCreates = new Map();
    }

    get size() {
        return this.owners.size;
    }

    /** Record a client request that is about to be forwarded under `proxyId`. */
    track(proxyId, client, msg) {
        if (msg.method === CREATE) {
            this.pendingCreates.set(proxyId, client);
        } else if (msg.method === DISPOSE && msg.params?.browserContextId) {
            // Chrome disposes whichever id it is given, so the context is gone whoever asked.
            this.owners.delete(msg.params.browserContextId);
        }
    }

    /** Call before Chrome's answer to `proxyId` is delivered: it carries the new context's id. */
    settle(proxyId, msg) {
        const client = this.pendingCreates.get(proxyId);
        if (!client) return;
        this.pendingCreates.delete(proxyId);
        const browserContextId = msg.result?.browserContextId;
        if (!browserContextId) return;
        if (client.closed === true) {
            this.log(`${client.label} left while creating browser context ${browserContextId}: disposing it`);
            this.dispose(browserContextId);
            return;
        }
        this.owners.set(browserContextId, client);
        this.log(`${client.label} create browser context ${browserContextId} (owned)`);
    }

    /** A forwarded creation request will never get an answer (timeout / Chrome exit). */
    abandon(proxyId) {
        this.pendingCreates.delete(proxyId);
    }

    /** Dispose the contexts the client created; its still-unanswered creation requests are settled on arrival. */
    onClientClosed(client) {
        const owned = [...this.owners].filter(([, owner]) => owner === client);
        for (const [browserContextId] of owned) {
            this.owners.delete(browserContextId);
            this.dispose(browserContextId);
        }
        if (owned.length) {
            this.log(`${client.label} disconnected: disposing ${owned.length} owned browser context(s)`);
        }
    }

    /** Chrome restarted: every context is gone. */
    reset() {
        this.owners.clear();
        this.pendingCreates.clear();
    }
}
