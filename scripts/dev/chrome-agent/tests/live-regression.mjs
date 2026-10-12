// Live regression for pipe-cdp-proxy session isolation.
//
// Spins up an isolated proxy + Chrome (random port, temp profile) and drives real
// chrome-devtools-mcp processes. Invariant under test: whatever other clients do
// (start, stop, attach, detach, exit), every live MCP's list_pages equals Chrome's
// real page set.
//
//   node tests/live-regression.mjs [--only t1,t2b] [--rounds 20] [--proxy-dir <dir>]
//
// --proxy-dir points at a directory holding another pipe-cdp-proxy.mjs (+ node_modules/ws),
// e.g. the pre-fix proxy: the isolation scenarios must then FAIL (negative control).
import http from 'node:http';
import { SandboxProxy, findMcpEntry, sleep } from './live/harness.mjs';

const argv = process.argv.slice(2);
const option = (name, fallback) => {
    const i = argv.indexOf(name);
    return i >= 0 ? argv[i + 1] : fallback;
};
const only = option('--only', '')?.split(',').filter(Boolean);
const ROUNDS = Number(option('--rounds', '8'));
const SETTLE_MS = 1500;

if (!findMcpEntry()) {
    console.log('SKIP: chrome-devtools-mcp not installed (npx chrome-devtools-mcp once, or set CHROME_DEVTOOLS_MCP_JS)');
    process.exit(0);
}

const proxy = new SandboxProxy(option('--proxy-dir', undefined));
const results = [];

async function check(label, condition, detail = '') {
    results.push({ label, ok: Boolean(condition), detail });
    console.log(`  ${condition ? 'ok  ' : 'FAIL'} ${label}${detail ? ` — ${detail}` : ''}`);
}

const truthCount = async () => (await proxy.chromePages()).length;

async function expectConsistent(label, ...mcps) {
    const truth = await truthCount();
    const counts = [];
    for (const mcp of mcps) counts.push((await mcp.pages()).length);
    await check(label, counts.every((n) => n === truth), `chrome=${truth} mcp=[${counts}]`);
}

/** Bare client: attach to every page, then optionally detach, then disconnect. */
async function bareAttach({ detach }) {
    const client = await proxy.cdp();
    const sessions = [];
    for (const page of await proxy.chromePages()) {
        const res = await client.send('Target.attachToTarget', { targetId: page.id, flatten: true });
        sessions.push(res.result?.sessionId);
    }
    if (detach) for (const sessionId of sessions) await client.send('Target.detachFromTarget', { sessionId });
    client.close();
}

const scenarios = {
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
        const leaked = listener.events.filter((e) => e.at >= exitedAt && e.method === 'Target.detachedFromTarget');
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

    // Chrome announces execution contexts only to the first Runtime.enable on a shared
    // session; a client that joins later (second MCP, or a restarted one) must still be
    // able to evaluate on pages it has not navigated itself.
    async lateJoiner() {
        const evaluates = async (mcp, label, expected) => {
            const pages = await mcp.pages();
            const seen = [];
            for (const { id } of pages) {
                await mcp.tool('select_page', { pageId: id });
                const r = await mcp.tool('evaluate_script', { pageId: id, function: '() => document.title' });
                seen.push(r.isError ? 'ERR' : r.text.includes(expected(id)) ? 'ok' : 'WRONG');
            }
            await check(`lateJoiner: ${label} evaluates on every page`, pages.length > 0 && seen.every((x) => x === 'ok'), seen.join(','));
        };
        const b = proxy.mcp('B'); await b.start();
        const [first, second] = await b.pages();
        await b.tool('select_page', { pageId: first.id });
        await b.tool('navigate_page', { pageId: first.id, type: 'url', url: 'data:text/html,<title>navigated</title>' });
        const expected = (id) => (id === first.id ? 'navigated' : '');
        const d = proxy.mcp('D'); await d.start();
        await evaluates(d, 'second client joining a live one', expected);
        for (const name of ['take_snapshot', 'take_screenshot']) {
            const r = await d.tool(name, { pageId: first.id });
            await check(`lateJoiner: second client ${name} works`, !r.isError, r.isError ? r.text.slice(0, 100) : '');
        }
        // The first page stays B's (tab lease); D navigates another one.
        await d.tool('select_page', { pageId: second.id });
        await d.tool('navigate_page', { pageId: second.id, type: 'url', url: 'data:text/html,<title>again</title>' });
        const afterNav = await b.tool('evaluate_script', { pageId: second.id, function: '() => document.title' });
        await check('lateJoiner: first client sees the second client\'s navigation', afterNav.text.includes('again'), afterNav.text.slice(0, 80));
        b.stop(); await sleep(1500);
        const f = proxy.mcp('F'); await f.start();
        const titles = (id) => (id === first.id ? 'navigated' : id === second.id ? 'again' : '');
        await evaluates(f, 'restarted client after the first one exited', titles);
        d.stop(); f.stop(); await sleep(1500);
        const g = proxy.mcp('G'); await g.start();
        await evaluates(g, 'client restarted while nobody else is connected', titles);
        g.stop();
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

    // Two sessions that pick "the first about:blank tab" at the same moment must never share a tab:
    // the loser is told to pick another one (TAB_LEASED) and then gets its own.
    async claimRace() {
        const [a, b] = [proxy.mcp('A'), proxy.mcp('B')];
        await a.start(); await b.start();
        let rejections = 0;
        const claim = async (mcp, tag) => {
            for (let attempt = 0; attempt < 4; attempt++) {
                const idle = (await mcp.pages()).find((p) => p.url === 'about:blank');
                if (!idle) return { tag, pageId: undefined };
                await mcp.tool('select_page', { pageId: idle.id });
                const r = await mcp.tool('navigate_page', { pageId: idle.id, type: 'url', url: `data:text/html,owner-${tag}` });
                if (/TAB_LEASED/.test(r.text)) { rejections++; continue; }
                return { tag, pageId: idle.id };
            }
            return { tag, pageId: undefined };
        };
        const owns = async (mcp, { tag, pageId }) => pageId !== undefined
            && (await mcp.tool('evaluate_script', { pageId, function: '() => location.href' })).text.includes(`owner-${tag}`);
        let collisions = 0;
        for (let round = 1; round <= ROUNDS; round++) {
            await a.pages(); await b.pages();
            const [ca, cb] = await Promise.all([claim(a, 'A'), claim(b, 'B')]);
            await sleep(300);
            const [okA, okB] = [await owns(a, ca), await owns(b, cb)];
            if (!okA || !okB) collisions++;
            await proxy.resetPages(3);
        }
        await check(`claimRace: ${ROUNDS} concurrent claims, every session kept its own tab`, collisions === 0, `collisions=${collisions} leaseRejections=${rejections}`);
        a.stop(); b.stop();
    },

    // Lease lifecycle: foreign navigation refused, reading allowed, release and disconnect both free the tab.
    async leaseLifecycle() {
        const [a, b] = [proxy.mcp('A'), proxy.mcp('B')];
        await a.start(); await b.start();
        const pageWith = async (mcp, marker) => (await mcp.pages()).find((p) => p.url.includes(marker))?.id;
        const navigate = (mcp, pageId, url) => mcp.tool('navigate_page', { pageId, type: 'url', url });
        const firstBlank = async (mcp) => (await mcp.pages()).find((p) => p.url === 'about:blank')?.id;

        const idA = await firstBlank(a);
        await navigate(a, idA, 'data:text/html,held-by-A');
        await b.pages();
        const idB = await pageWith(b, 'held-by-A');
        const refused = await navigate(b, idB, 'data:text/html,hijack');
        await check('leaseLifecycle: foreign navigation is refused', /TAB_LEASED/.test(refused.text), refused.text.slice(0, 90));
        // Only navigation is arbitrated: a raw client can still talk to the leased tab.
        const raw = await proxy.cdp();
        const target = (await proxy.chromePages()).find((p) => p.url.includes('held-by-A'));
        const { result } = await raw.send('Target.attachToTarget', { targetId: target.id, flatten: true });
        const read = await raw.send('Runtime.evaluate', { expression: 'location.href' }, result.sessionId);
        await check('leaseLifecycle: non-navigation commands on a leased tab still work', String(read.result?.result?.value).includes('held-by-A'));
        raw.close();
        const stillA = (await a.tool('evaluate_script', { pageId: idA, function: '() => location.href' })).text.includes('held-by-A');
        await check('leaseLifecycle: lessee page untouched by the refused navigation', stillA);

        await navigate(a, idA, 'about:blank');
        await b.pages();
        const claimed = await navigate(b, await pageWith(b, 'about:blank') ?? idB, 'data:text/html,now-B');
        await check('leaseLifecycle: released tab can be claimed by the other session', !/TAB_LEASED/.test(claimed.text), claimed.text.slice(0, 90));

        const idA2 = await firstBlank(a);
        await navigate(a, idA2, 'data:text/html,A-then-dies');
        a.stop();
        await sleep(1500);
        await b.pages();
        const idB2 = await pageWith(b, 'A-then-dies');
        const afterDeath = await navigate(b, idB2, 'about:blank');
        await check('leaseLifecycle: a disconnected lessee no longer blocks the tab', !/TAB_LEASED/.test(afterDeath.text), afterDeath.text.slice(0, 90));
        b.stop();
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

    // Real-world surfaces: cross-site iframe, popup, worker, plus one call of the common tools.
    async behaviour() {
        const frameServer = http.createServer((_, res) => { res.setHeader('content-type', 'text/html'); res.end('<p id="in">inner</p>'); });
        await new Promise((r) => frameServer.listen(0, '127.0.0.1', r));
        const framePort = frameServer.address().port;
        const pageServer = http.createServer((_, res) => {
            res.setHeader('content-type', 'text/html');
            res.end(`<iframe id="f" src="http://localhost:${framePort}/"></iframe><button id="b" onclick="window.open('about:blank#popup')">pop</button>`);
        });
        await new Promise((r) => pageServer.listen(0, '127.0.0.1', r));
        const url = `http://127.0.0.1:${pageServer.address().port}/`;

        const b = proxy.mcp('B'); await b.start();
        const d = proxy.mcp('D'); await d.start(); await d.pages();
        const tool = async (name, args) => {
            const r = await b.tool(name, args);
            await check(`behaviour: ${name} succeeds`, !r.isError, r.isError ? r.text.slice(0, 120) : '');
            return r;
        };
        await tool('new_page', { url });
        const pages = await b.pages();
        const pageId = pages.find((p) => p.url.startsWith('http://127.0.0.1'))?.id;
        await check('behaviour: new page listed', pageId !== undefined);
        await sleep(1500);
        await tool('select_page', { pageId });
        await tool('take_snapshot', { pageId });
        await tool('take_screenshot', { pageId });
        await tool('resize_page', { pageId, width: 900, height: 700 });
        await tool('list_console_messages', { pageId });
        await tool('list_network_requests', { pageId });
        const worker = await tool('evaluate_script', {
            pageId,
            function: `() => new Promise((resolve) => {
                const w = new Worker(URL.createObjectURL(new Blob(['postMessage(21*2)'])));
                w.onmessage = (e) => resolve('worker:' + e.data);
            })`,
        });
        await check('behaviour: web worker round-trips', worker.text.includes('worker:42'), worker.text.slice(0, 80));
        const frames = await tool('evaluate_script', { pageId, function: '() => document.getElementById("f") ? "iframe-present" : "none"' });
        await check('behaviour: cross-site iframe present', frames.text.includes('iframe-present'));
        await tool('evaluate_script', { pageId, function: '() => { window.open("about:blank#popup"); return "opened"; }' });
        await sleep(1500);
        await tool('navigate_page', { pageId, type: 'url', url: `${url}?n=2` });
        await expectConsistent('behaviour: B and D consistent after popup + navigation', b, d);
        await tool('close_page', { pageId });
        await sleep(1500);
        await expectConsistent('behaviour: B and D consistent after close_page', b, d);
        b.stop(); await sleep(2500);
        await expectConsistent('behaviour: D consistent after B exits', d);
        d.stop(); frameServer.close(); pageServer.close();
    },
};

await proxy.start();
console.log(`sandbox proxy on ${proxy.base} (log: ${proxy.logPath})`);
const selected = only?.length ? only : Object.keys(scenarios);
for (const name of selected) {
    console.log(`\n[${name}]`);
    try {
        await proxy.resetPages(3);
        await scenarios[name]();
    } catch (err) {
        await check(`${name}: scenario completed`, false, err.message);
    }
}
const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
if (failed.length) console.log(`FAILED:\n${failed.map((r) => `  - ${r.label} ${r.detail}`).join('\n')}`);
proxy.stop();
process.exit(failed.length ? 1 : 0);
