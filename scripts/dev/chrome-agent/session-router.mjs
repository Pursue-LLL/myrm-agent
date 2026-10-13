/**
 * session-router — CDP session ownership + base-session cache for pipe-cdp-proxy.
 *
 * Two kinds of Chrome sessions flow through the proxy:
 *
 *   base    Created by the proxy's own Target.setAutoAttach (and their iframe/worker
 *           children). One per target, shared by every client: cached, replayed to
 *           late clients, events broadcast.
 *   owned   Created by a client's own Target.attachToTarget (e.g. chrome-devtools-mcp's
 *           DevTools session per page). Private to that client: never cached, never
 *           replayed, attach/detach/session events go to the owner only, nobody else
 *           may detach it, and it is detached when the owner disconnects.
 *
 * Why: puppeteer deletes a whole page from its registry when it sees
 * `detachedFromTarget` for a session it did not create. Broadcasting or replaying one
 * client's private sessions therefore made every other client lose all its pages
 * the moment that client attached, detached, or exited.
 *
 * The router also owns the idle-tab lease (tab-lease.mjs), because it already knows which
 * target every session belongs to, and the execution-context replay for late joiners of a
 * shared session (context-replay.mjs), because it already sees every base-session event.
 *
 * `describeSession` resolves a session to "<owned|base> <type> <current url>" for the
 * slow-request log (request-watch.mjs); `pageOfSession` and `baseSessionOfPage` resolve the page
 * behind a stuck request and the shared session to probe it with (hang-guard.mjs).
 *
 * The router does no I/O: the proxy injects delivery and detach callbacks, which keeps
 * every routing rule unit-testable without Chrome.
 */

import { TabLease, LEASE_REJECT_CODE } from './tab-lease.mjs';
import { ContextReplay } from './context-replay.mjs';

const ATTACHED = 'Target.attachedToTarget';
const DETACHED = 'Target.detachedFromTarget';
const ATTACH_METHODS = new Set(['Target.attachToTarget', 'Target.attachToBrowserTarget']);
/** An owner-less session whose detach event never arrives must not leak forever. */
const ORPHAN_TTL_MS = 30_000;

const ATTRIBUTED_METHODS = new Set([
    'Page.navigate', 'Page.reload', 'Page.navigateToHistoryEntry',
    'Target.createTarget', 'Target.closeTarget',
]);

export const isAttachMethod = (method) => ATTACH_METHODS.has(method);

/**
 * Give a client-created tab its own window unless the client chose explicitly.
 *
 * Tabs sharing a window are hidden except the front one, and macOS runs the hidden tabs'
 * renderers at background priority (PRI 4): under host load they starve and every CDP call
 * on them times out. puppeteer/chrome-devtools-mcp `newPage()` never sets `newWindow`, so
 * without this a `new_page` lands in an existing window. Mutates `msg` in place; returns
 * true when it injected the flag. Applied on the forward path of `classifyClientRequest`.
 */
export function ensureOwnWindow(msg) {
    if (msg.method !== 'Target.createTarget') return false;
    if (msg.params?.newWindow !== undefined) return false;
    msg.params = { ...msg.params, newWindow: true };
    return true;
}

export class SessionRouter {
    /**
     * @param {object} hooks
     * @param {(msg: object, to: 'all' | object) => void} hooks.deliver  send to every client or one client
     * @param {(sessionId: string) => void} hooks.detachSession  ask Chrome to detach an orphaned session
     * @param {(line: string) => void} hooks.log  attribution log sink
     */
    constructor({ deliver, detachSession, log }) {
        this.deliver = deliver;
        this.detachSession = detachSession;
        this.log = log;
        /** sessionId → { owner: client | null, targetId, parent: sessionId | null, orphanedAt: number | null } */
        this.owned = new Map();
        /** proxyId → { client, method, targetId } for attach requests awaiting a response */
        this.pendingAttach = new Map();
        /** browser-level attachedToTarget events whose owner is not known yet (event precedes response) */
        this.held = [];
        this.knownTargets = new Map();
        this.knownSessions = new Map();
        this.tabLease = new TabLease({ urlOf: (targetId) => this.knownTargets.get(targetId)?.url, log });
        /** proxyId → { targetId, client } for forwarded navigations that acquired a tab lease */
        this.pendingLease = new Map();
        this.contextReplay = new ContextReplay();
    }

    // ── client → Chrome ─────────────────────────────────────────────

    /** Decide whether a client request is forwarded to Chrome or answered locally. */
    classifyClientRequest(client, msg) {
        const { rejected, acquired } = this.tabLease.guard(client, this.targetOfSession(msg.sessionId), msg);
        if (rejected) {
            return { action: 'reply', error: { code: LEASE_REJECT_CODE, message: rejected } };
        }
        const sessionId = msg.params?.sessionId;
        if (msg.method !== 'Target.detachFromTarget' || !sessionId) {
            ensureOwnWindow(msg);
            return { action: 'forward', acquiredLease: acquired };
        }
        if (this.owned.get(sessionId)?.owner === client) {
            return { action: 'forward' };
        }
        // Detaching a shared or foreign session would delete the page for other clients.
        // Answer success so the caller's own bookkeeping completes; nothing reaches Chrome.
        this.log(`${client.label} detach ${short(sessionId)} blocked (${this.#describeUnowned(sessionId)})`);
        return { action: 'reply', result: {} };
    }

    /** Attribute requests that change what other clients see (navigations, tab open/close) to the connection. */
    logRequest(client, msg) {
        if (!ATTRIBUTED_METHODS.has(msg.method)) return;
        const target = this.targetOfSession(msg.sessionId) ?? msg.params?.targetId;
        const url = msg.params?.url ? ` url=${String(msg.params.url).slice(0, 120)}` : '';
        this.log(`${client.label} ${msg.method} target=${short(target)}${url}`);
    }

    /** Record a request that is about to be forwarded under `proxyId` (`decision` is classifyClientRequest's). */
    trackForwardedRequest(client, msg, proxyId, decision) {
        // Owned sessions are private (fresh Chrome state); only shared sessions need replay.
        if (!this.owned.has(msg.sessionId)) this.contextReplay.track(proxyId, client, msg);
        if (decision?.acquiredLease) {
            this.pendingLease.set(proxyId, { targetId: decision.acquiredLease, client });
        }
        if (!ATTACH_METHODS.has(msg.method)) return;
        this.pendingAttach.set(proxyId, {
            client,
            method: msg.method,
            targetId: msg.params?.targetId,
        });
    }

    // ── Chrome → client ─────────────────────────────────────────────

    /** Call before the response is delivered, so the attach event reaches the owner first. */
    onChromeResponse(proxyId, msg) {
        const replay = this.contextReplay.settle(proxyId, msg);
        if (replay) {
            for (const event of replay.events) this.deliver(event, replay.client);
        }
        const lease = this.pendingLease.get(proxyId);
        if (lease) {
            this.pendingLease.delete(proxyId);
            if (msg.error) this.tabLease.revoke(lease.targetId, lease.client);
        }
        const pending = this.pendingAttach.get(proxyId);
        if (!pending) return;
        this.pendingAttach.delete(proxyId);
        const sessionId = msg.result?.sessionId;
        if (sessionId) {
            this.#adopt(sessionId, pending);
        }
        this.#releaseUnclaimedHeld();
    }

    /** A forwarded attach request will never get a response (timeout / Chrome exit). */
    onRequestAbandoned(proxyId) {
        this.contextReplay.abandon(proxyId);
        this.pendingLease.delete(proxyId);
        if (this.pendingAttach.delete(proxyId)) {
            this.#releaseUnclaimedHeld();
        }
    }

    /** Route one Chrome event (a message without `id`). */
    onChromeEvent(msg) {
        const { method, sessionId: from, params } = msg;
        const isAttachEvent = method === ATTACHED || method === DETACHED;
        const subject = isAttachEvent ? params?.sessionId : undefined;

        // Inside a private session subtree (iframe / worker children inherit the owner).
        const fromEntry = from ? this.owned.get(from) : undefined;
        if (fromEntry) {
            if (method === ATTACHED && subject) {
                this.owned.set(subject, {
                    owner: fromEntry.owner,
                    targetId: params.targetInfo?.targetId ?? fromEntry.targetId,
                    parent: from,
                    orphanedAt: fromEntry.orphanedAt,
                });
            } else if (method === DETACHED && subject) {
                this.owned.delete(subject);
            }
            this.#toOwner(fromEntry, msg);
            return;
        }

        // Browser-level attach/detach of a private session.
        const subjectEntry = subject ? this.owned.get(subject) : undefined;
        if (subjectEntry) {
            if (method === DETACHED) this.#forget(subject);
            this.#toOwner(subjectEntry, msg);
            return;
        }

        // Possibly the answer to a client's attachToTarget: Chrome emits the event before
        // the response, so ownership is unknown until the response carries the sessionId.
        if (method === ATTACHED && !from && subject && this.#isClaimable(params.targetInfo)) {
            this.held.push(msg);
            return;
        }

        this.#routeBase(msg);
    }

    // ── lifecycle ───────────────────────────────────────────────────

    /** Orphan the client's private sessions and detach them in Chrome (no broadcast to others). */
    onClientClosed(client) {
        this.contextReplay.dropClient(client);
        this.tabLease.onClientClosed(client);
        for (const [proxyId, lease] of this.pendingLease) {
            if (lease.client === client) this.pendingLease.delete(proxyId);
        }
        const now = Date.now();
        const detached = [];
        for (const [sessionId, entry] of this.owned) {
            if (entry.owner !== client) continue;
            entry.owner = null;
            entry.orphanedAt = now;
            if (!entry.parent) detached.push(sessionId);
        }
        for (const sessionId of detached) {
            this.detachSession(sessionId);
        }
        if (detached.length) {
            this.log(`${client.label} disconnected: detaching ${detached.length} owned session(s)`);
        }
    }

    /** Chrome restarted: every session and cached target is gone. */
    reset() {
        this.owned.clear();
        this.pendingAttach.clear();
        this.pendingLease.clear();
        this.tabLease.reset();
        this.contextReplay.reset();
        this.held = [];
        this.knownTargets.clear();
        this.knownSessions.clear();
    }

    /** Drop orphaned entries whose detach event never came. */
    purgeOrphans(now = Date.now()) {
        for (const [sessionId, entry] of this.owned) {
            if (entry.orphanedAt !== null && now - entry.orphanedAt > ORPHAN_TTL_MS) {
                this.owned.delete(sessionId);
            }
        }
    }

    // ── base-session cache (replayed to late clients) ───────────────

    replayDiscovery(client) {
        for (const [, targetInfo] of this.knownTargets) {
            this.deliver({ method: 'Target.targetCreated', params: { targetInfo } }, client);
        }
    }

    /** Replays parents before children (Map order = attach order); a child keeps its parent's envelope. */
    replayAutoAttach(client) {
        for (const [sessionId, { targetInfo, waitingForDebugger, parentSessionId }] of this.knownSessions) {
            this.deliver(
                {
                    method: ATTACHED,
                    params: { sessionId, targetInfo, waitingForDebugger },
                    ...(parentSessionId && { sessionId: parentSessionId }),
                },
                client,
            );
        }
    }

    // ── introspection ───────────────────────────────────────────────

    targetOfSession(sessionId) {
        return this.owned.get(sessionId)?.targetId
            ?? this.knownSessions.get(sessionId)?.targetInfo?.targetId;
    }

    /** What a session is attached to, for logs: "<owned|base> <target type> <url>"; null when unknown. */
    describeSession(sessionId) {
        const owned = this.owned.get(sessionId);
        // knownTargets follows navigation (targetInfoChanged); a base session's own targetInfo is its attach-time snapshot.
        const info = this.knownTargets.get(this.targetOfSession(sessionId)) ?? this.knownSessions.get(sessionId)?.targetInfo;
        if (!info) return null;
        return `${owned ? 'owned' : 'base'} ${info.type} ${(info.url || 'about:blank').slice(0, 60)}`;
    }

    /**
     * The `page` target a session ultimately belongs to, following iframe/worker sessions up to
     * their parent; null when the session is unknown or its root is not a page. Used to attribute
     * an unanswered request to the page whose renderer is stuck (hang-guard.mjs).
     */
    pageOfSession(sessionId) {
        let id = sessionId;
        for (let hops = 0; id && hops < 16; hops++) {
            const owned = this.owned.get(id);
            const known = this.knownSessions.get(id);
            const parent = owned ? owned.parent : known?.parentSessionId;
            if (parent) {
                id = parent;
                continue;
            }
            const targetId = owned?.targetId ?? known?.targetInfo?.targetId;
            return this.knownTargets.get(targetId)?.type === 'page' ? targetId : null;
        }
        return null;
    }

    /** A shared base session attached to the page itself (not to one of its frames or workers). */
    baseSessionOfPage(targetId) {
        for (const [sessionId, { targetInfo, parentSessionId }] of this.knownSessions) {
            if (!parentSessionId && targetInfo?.targetId === targetId) return sessionId;
        }
        return undefined;
    }

    ownedCountOf(client) {
        let count = 0;
        for (const entry of this.owned.values()) {
            if (entry.owner === client) count++;
        }
        return count;
    }

    // ── internals ───────────────────────────────────────────────────

    #adopt(sessionId, pending) {
        const { client, targetId } = pending;
        const orphaned = client.closed === true;
        this.owned.set(sessionId, {
            owner: orphaned ? null : client,
            targetId,
            parent: null,
            orphanedAt: orphaned ? Date.now() : null,
        });
        this.log(`${client.label} attach ${short(sessionId)} target=${short(targetId)} (owned)`);
        const heldIdx = this.held.findIndex((m) => m.params.sessionId === sessionId);
        if (heldIdx >= 0) {
            const [event] = this.held.splice(heldIdx, 1);
            this.#toOwner(this.owned.get(sessionId), event);
        }
        if (orphaned) {
            // The client left while its attach was in flight; nobody will ever detach it.
            this.detachSession(sessionId);
        }
    }

    /** True if some in-flight attach request could be the origin of an attach event for this target. */
    #isClaimable(targetInfo) {
        for (const pending of this.pendingAttach.values()) {
            if (pending.method === 'Target.attachToBrowserTarget') {
                if (targetInfo?.type === 'browser') return true;
            } else if (pending.targetId && pending.targetId === targetInfo?.targetId) {
                return true;
            }
        }
        return false;
    }

    /** Held events that no remaining request can claim are ordinary base-session events. */
    #releaseUnclaimedHeld() {
        if (!this.held.length) return;
        const stillHeld = [];
        for (const msg of this.held) {
            if (this.#isClaimable(msg.params.targetInfo)) {
                stillHeld.push(msg);
            } else {
                this.#routeBase(msg);
            }
        }
        this.held = stillHeld;
    }

    #routeBase(msg) {
        this.#cacheBase(msg);
        this.deliver(msg, 'all');
    }

    #cacheBase(msg) {
        const { method, params } = msg;
        this.contextReplay.observe(msg);
        if (method === 'Target.targetCreated' || method === 'Target.targetInfoChanged') {
            if (params?.targetInfo) this.knownTargets.set(params.targetInfo.targetId, params.targetInfo);
        } else if (method === 'Target.targetDestroyed') {
            if (params?.targetId) {
                this.knownTargets.delete(params.targetId);
                this.tabLease.forget(params.targetId);
            }
        } else if (method === ATTACHED && params?.sessionId) {
            this.knownSessions.set(params.sessionId, {
                targetInfo: params.targetInfo,
                waitingForDebugger: params.waitingForDebugger ?? false,
                parentSessionId: msg.sessionId,
            });
            if (params.targetInfo) this.knownTargets.set(params.targetInfo.targetId, params.targetInfo);
        } else if (method === DETACHED && params?.sessionId) {
            this.#forgetBase(params.sessionId);
        }
    }

    /** Drops a base session and its descendants: a child is unreachable once its parent is gone. */
    #forgetBase(sessionId) {
        this.knownSessions.delete(sessionId);
        this.contextReplay.forget(sessionId);
        for (const [childId, { parentSessionId }] of this.knownSessions) {
            if (parentSessionId === sessionId) this.#forgetBase(childId);
        }
    }

    #toOwner(entry, msg) {
        if (entry.owner) this.deliver(msg, entry.owner);
    }

    /** Remove a session and its subtree after Chrome reported it detached. */
    #forget(sessionId) {
        this.owned.delete(sessionId);
        for (const [childId, entry] of this.owned) {
            if (entry.parent === sessionId) this.#forget(childId);
        }
    }

    #describeUnowned(sessionId) {
        const owner = this.owned.get(sessionId)?.owner;
        if (owner) return `owned by ${owner.label}`;
        return this.knownSessions.has(sessionId) ? 'shared base session' : 'unknown session';
    }
}

export const short = (id) => (id ? String(id).slice(0, 8) : '-');
