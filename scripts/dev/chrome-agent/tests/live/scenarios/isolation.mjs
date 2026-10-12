// Page-registry isolation: whatever other clients do (start, stop, attach, detach, exit),
// every live MCP keeps seeing exactly the pages Chrome has.
import { sleep } from '../harness.mjs';

export const isolationScenarios = ({ proxy, check, expectConsistent, bareAttach, ROUNDS, SETTLE_MS }) => ({
    // A client that exits must not cost other clients their pages (the original incident).
    async t2b() {
        const b = proxy.mcp('B'); await b.start();
        await b.pages();
        const listener = await proxy.listener();
        const c = proxy.mcp('C'); await c.start();
        await c.pages();
        await expectConsistent('t2b: B consistent while C alive', b);
        const exitedAt = Date.now();
        c.stop();
        await sleep(3000);
        await expectConsistent('t2b: B consistent 3s after C exits', b);
        // Chrome-internal targets (type 'other') detach on their own schedule; only page sessions are C's.
        const leaked = listener.events.filter((e) => e.at >= exitedAt && e.method === 'Target.detachedFromTarget' && (e.type === undefined || e.type === 'page'));
        await check('t2b: bystander sees no detach events from C exiting', leaked.length === 0, `${leaked.length} events`);
        await sleep(5000);
        await expectConsistent('t2b: B still consistent 8s after C exits', b);
        listener.close(); b.stop();
    },

    async t2c() {
        const [b, d, c] = [proxy.mcp('B'), proxy.mcp('D'), proxy.mcp('C')];
        await b.start(); await d.start(); await c.start();
        await b.pages(); await d.pages(); await c.pages();
        c.stop();
        await sleep(3000);
        await expectConsistent('t2c: B and D consistent after C exits', b, d);
        b.stop(); d.stop();
    },

    // Raw attach + explicit detach by a non-MCP client.
    async t1() {
        const b = proxy.mcp('B'); await b.start(); await b.pages();
        await bareAttach({ detach: true });
        await sleep(3000);
        const fresh = proxy.mcp('F'); await fresh.start();
        await expectConsistent('t1: B and a fresh MCP consistent after bare attach+detach', b, fresh);
        b.stop(); fresh.stop();
    },

    // Raw attach, then disconnect without detach: the proxy must clean up the orphans.
    async t3() {
        const b = proxy.mcp('B'); await b.start(); await b.pages();
        await bareAttach({ detach: false });
        await sleep(3000);
        await expectConsistent('t3: B consistent after bare attach+disconnect', b);
        const status = await proxy.status();
        const attributed = status.connections.reduce((n, c) => n + c.ownedSessions, 0);
        await check('t3: no orphaned sessions after the owner disconnected', status.ownedSessions === attributed, `owned=${status.ownedSessions} attributed=${attributed}`);
        b.stop();
    },

    // MCP stays consistent for as long as we watch and sees pages created later.
    async t4() {
        const b = proxy.mcp('B'); await b.start(); await b.pages();
        const c = proxy.mcp('C'); await c.start(); await c.pages(); c.stop();
        for (const wait of [3000, 7000, 10000]) {
            await sleep(wait);
            await expectConsistent(`t4: B consistent after another +${wait / 1000}s`, b);
        }
        const client = await proxy.cdp();
        await client.send('Target.createTarget', { url: 'about:blank' });
        client.close();
        await sleep(2000);
        await expectConsistent('t4: B sees a page created by someone else', b);
        b.stop();
    },

    // A client connecting AFTER another client's private session exists must not inherit it.
    async t5() {
        const b = proxy.mcp('B'); await b.start(); await b.pages();
        const client = await proxy.cdp();
        const [page] = await proxy.chromePages();
        const attach = await client.send('Target.attachToTarget', { targetId: page.id, flatten: true });
        const d = proxy.mcp('D'); await d.start();
        await expectConsistent('t5: D consistent while A holds a private session', d, b);
        await client.send('Target.detachFromTarget', { sessionId: attach.result.sessionId });
        await sleep(3000);
        await expectConsistent('t5: D and B consistent after A detaches', d, b);
        client.close(); b.stop(); d.stop();
    },

    // A client may not detach a session it does not own; its own detach still works.
    async detachGuard() {
        const [owner, other] = [await proxy.cdp(), await proxy.cdp()];
        const [page] = await proxy.chromePages();
        const attach = await owner.send('Target.attachToTarget', { targetId: page.id, flatten: true });
        const sessionId = attach.result.sessionId;
        const foreign = await other.send('Target.detachFromTarget', { sessionId });
        await check('detachGuard: foreign detach is answered without error', foreign.result && !foreign.error);
        const alive = await owner.send('Runtime.evaluate', { expression: '1+1' }, sessionId);
        await check('detachGuard: owner session survives a foreign detach', alive.result?.result?.value === 2);
        const own = await owner.send('Target.detachFromTarget', { sessionId });
        await check('detachGuard: owner can detach its own session', own.result && !own.error);
        const dead = await owner.send('Runtime.evaluate', { expression: '1+1' }, sessionId);
        await check('detachGuard: session is gone after the owner detached', Boolean(dead.error));
        owner.close(); other.close();
    },

    // Randomized start/stop/attach churn with 4 MCPs.
    async churn() {
        let seed = 1234567;
        const rand = (n) => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed % n; };
        const live = new Map();
        let serial = 0;
        const startOne = async () => {
            const mcp = proxy.mcp(`M${serial++}`); await mcp.start(); await mcp.pages();
            live.set(mcp.name, mcp);
        };
        await startOne(); await startOne();
        for (let round = 1; round <= ROUNDS; round++) {
            const op = rand(5);
            let label;
            if (op === 0 && live.size < 4) { await startOne(); label = 'start'; }
            else if (op === 1 && live.size > 1) {
                const [name, mcp] = [...live][rand(live.size)];
                mcp.stop(); live.delete(name); label = `stop ${name}`;
            } else if (op === 2) { await bareAttach({ detach: true }); label = 'bare attach+detach'; }
            else if (op === 3) { await bareAttach({ detach: false }); label = 'bare attach+drop'; }
            else {
                const client = await proxy.cdp();
                await client.send('Target.createTarget', { url: 'about:blank' });
                client.close(); label = 'new page';
            }
            await sleep(SETTLE_MS);
            await expectConsistent(`churn ${round}/${ROUNDS} (${label}): all ${live.size} MCPs consistent`, ...live.values());
        }
        for (const mcp of live.values()) mcp.stop();
    },
});
