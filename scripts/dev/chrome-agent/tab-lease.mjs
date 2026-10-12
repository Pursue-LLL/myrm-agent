/**
 * tab-lease — first-navigator-wins arbitration for the shared idle tabs of pipe-cdp-proxy.
 *
 * Every session sees the same list of `about:blank` tabs and picks one, then navigates it.
 * Between its list_pages and its Page.navigate another session may have picked the same
 * tab, and the later navigation silently overwrote the earlier one. The proxy is the only
 * place that sees both navigations, so it decides there:
 *
 *   - navigating a tab to a real URL leases the tab to that connection;
 *   - while the lease is live, navigating (or reloading, or history-stepping) the tab from
 *     any other connection is rejected with an instruction to pick another idle tab;
 *   - the lessee releases by navigating the tab back to about:blank, or by disconnecting.
 *
 * The lease is bound to the connection, not to a time window, so a long-running task never
 * loses its tab; only a leased tab that sits blank (nobody committed a page into it) is
 * reclaimed after STALE_BLANK_MS. Reading (evaluate, screenshot, ...) is not restricted.
 *
 * A lessee that disconnects without releasing leaves its tab on a page nobody will ever
 * navigate back to about:blank. Such a tab is remembered as abandoned; the idle pool takes
 * it back once nobody has claimed or released it for a grace period (takeAbandoned).
 */

const GUARDED_METHODS = new Set(['Page.navigate', 'Page.reload', 'Page.navigateToHistoryEntry']);
/** A leased tab still showing about:blank this long after the lease started never loaded. */
const STALE_BLANK_MS = 60_000;
const BLANK = 'about:blank';

export const LEASE_REJECT_CODE = -32002;

export class TabLease {
    /**
     * @param {object} hooks
     * @param {(targetId: string) => string | undefined} hooks.urlOf  last URL Chrome reported for a target
     * @param {(line: string) => void} hooks.log
     * @param {() => number} [hooks.now]
     */
    constructor({ urlOf, log, now = Date.now }) {
        this.urlOf = urlOf;
        this.log = log;
        this.now = now;
        /** targetId → { owner: client, since: number } */
        this.leases = new Map();
        /** targetId → when its lessee disconnected without releasing the tab */
        this.abandoned = new Map();
    }

    /**
     * Decide one client request.
     * @returns {{ rejected?: string, acquired?: string }} `rejected` is the error text to send
     *   back; `acquired` is the targetId leased by this very request (revoked if Chrome refuses it).
     */
    guard(client, targetId, msg) {
        if (!targetId || !GUARDED_METHODS.has(msg.method)) return {};
        const lease = this.#liveLease(targetId);
        if (lease && lease.owner !== client) {
            const seconds = Math.round((this.now() - lease.since) / 1000);
            this.log(`${client.label} ${msg.method} target=${targetId.slice(0, 8)} rejected (leased by ${lease.owner.label} ${seconds}s ago)`);
            return {
                rejected: `TAB_LEASED: this tab was claimed by another session ${seconds}s ago. `
                    + 'Do not touch it. Call list_pages again and pick a different about:blank tab; '
                    + 'if none is left, report NO_IDLE_TAB',
            };
        }
        if (msg.method !== 'Page.navigate') return {};
        if (msg.params?.url === BLANK) {
            this.leases.delete(targetId);
            this.abandoned.delete(targetId);
            return {};
        }
        if (lease) return {};
        this.abandoned.delete(targetId);
        this.leases.set(targetId, { owner: client, since: this.now() });
        return { acquired: targetId };
    }

    /** Chrome refused the navigation that acquired the lease: the tab is still idle. */
    revoke(targetId, client) {
        if (this.leases.get(targetId)?.owner === client) this.leases.delete(targetId);
    }

    /** The tab itself is gone. */
    forget(targetId) {
        this.leases.delete(targetId);
        this.abandoned.delete(targetId);
    }

    onClientClosed(client) {
        for (const [targetId, lease] of this.leases) {
            if (lease.owner !== client) continue;
            this.leases.delete(targetId);
            const url = this.urlOf(targetId);
            if (url && url !== BLANK) this.abandoned.set(targetId, this.now());
        }
    }

    /** Tabs abandoned for at least `graceMs` (removed from the registry; callers re-check before acting). */
    takeAbandoned(graceMs) {
        const expired = [];
        for (const [targetId, since] of this.abandoned) {
            if (this.now() - since >= graceMs) {
                expired.push(targetId);
                this.abandoned.delete(targetId);
            }
        }
        return expired;
    }

    reset() {
        this.leases.clear();
        this.abandoned.clear();
    }

    /** The lease on a target, after dropping it when its owner is gone or it never loaded. */
    #liveLease(targetId) {
        const lease = this.leases.get(targetId);
        if (!lease) return undefined;
        const neverLoaded = this.urlOf(targetId) === BLANK && this.now() - lease.since > STALE_BLANK_MS;
        if (lease.owner.closed || neverLoaded) {
            this.leases.delete(targetId);
            return undefined;
        }
        return lease;
    }
}
