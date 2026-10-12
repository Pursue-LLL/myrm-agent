// Live regression for the abandoned-tab reclaim of idle-pool.mjs (headless sandbox, random port).
//
//   node tests/live-pool-regression.mjs [--proxy-dir <dir>]
//
// A session that disconnects while its tab still shows a page leaves that tab behind. With a
// short grace period the proxy must close it and refill the pool, while a tab whose session is
// still connected, or that was released to about:blank, must never be touched.
import { SandboxProxy, sleep } from './live/harness.mjs';

const argv = process.argv.slice(2);
const dirFlag = argv.indexOf('--proxy-dir');
const proxy = new SandboxProxy(dirFlag >= 0 ? argv[dirFlag + 1] : undefined, {
    CHROME_AGENT_MIN_IDLE_TABS: '3',
    CHROME_AGENT_MAX_PAGES: '5',
    CHROME_AGENT_ABANDON_GRACE_MS: '3000',
});
const results = [];
const check = (label, ok, detail = '') => {
    results.push({ label, ok: Boolean(ok), detail });
    console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${label}${detail ? ` — ${detail}` : ''}`);
};

const urls = async () => (await proxy.chromePages()).map((p) => p.url);
const blanks = async () => (await urls()).filter((u) => u === 'about:blank').length;
const waitFor = async (predicate, ms = 12000) => {
    for (let waited = 0; waited < ms; waited += 500) {
        if (await predicate()) return true;
        await sleep(500);
    }
    return false;
};

/** Connect, navigate the first idle tab to `marker`, optionally release it; returns the client. */
async function claim(marker, { release = false } = {}) {
    const client = await proxy.cdp();
    const page = (await proxy.chromePages()).find((p) => p.url === 'about:blank');
    const { result } = await client.send('Target.attachToTarget', { targetId: page.id, flatten: true });
    await client.send('Page.navigate', { url: `data:text/html,${marker}` }, result.sessionId);
    await sleep(500);
    if (release) await client.send('Page.navigate', { url: 'about:blank' }, result.sessionId);
    return client;
}
const hasMarker = async (marker) => (await urls()).some((u) => u.includes(marker));

await proxy.start();
console.log(`sandbox proxy on ${proxy.base}`);
await waitFor(async () => (await blanks()) === 3);

console.log('\n[abandonedTabs]');
const connected = await claim('still-connected');
const released = await claim('released', { release: true });
const leaker = await claim('leaked');
leaker.close();
await sleep(1000);
check('leaked tab survives the grace period', await hasMarker('leaked'));
const reclaimed = await waitFor(async () => !(await hasMarker('leaked')));
check('a tab abandoned by a disconnected session is closed after the grace period', reclaimed, (await urls()).join(' | ').slice(0, 160));
await sleep(4000);
check('a tab whose session is still connected is never touched', await hasMarker('still-connected'));
connected.close();
released.close();
check('the pool is refilled after the reclaim', await waitFor(async () => (await blanks()) >= 3), `blank=${await blanks()}`);

console.log('\n[capLeak]');
for (let i = 0; i < 4; i++) (await claim(`leak-${i}`)).close();
check('every leaked tab is reclaimed and the pool recovers within the cap',
    await waitFor(async () => (await blanks()) >= 3 && (await proxy.chromePages()).length <= 5, 20000),
    `blank=${await blanks()} total=${(await proxy.chromePages()).length}`);
const fresh = await claim('fresh-after-leaks');
check('a new session still finds an idle tab after the leaks', await hasMarker('fresh-after-leaks'));
fresh.close();

const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
proxy.stop({ keepLog: failed.length > 0 });
process.exit(failed.length ? 1 : 0);
