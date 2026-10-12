// Tab ownership: concurrent claim of one tab, lease lifecycle, idle-tab pool.
import fs from 'node:fs';
import { SandboxProxy, sleep } from '../harness.mjs';

export const tabScenarios = ({ proxy, check, option, ROUNDS }) => ({

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

    // The proxy keeps a floor of idle tabs: a fresh Chrome has one tab, every claim consumes one,
    // and sessions may not open tabs themselves. Runs on its own proxy with the pool enabled.
    async idlePool() {
        const pooled = new SandboxProxy(option('--proxy-dir', undefined), {
            CHROME_AGENT_MIN_IDLE_TABS: '3', CHROME_AGENT_MAX_PAGES: '5',
        });
        await pooled.start();
        const blanks = async () => (await pooled.chromePages()).filter((p) => p.url === 'about:blank').length;
        const total = async () => (await pooled.chromePages()).length;
        const waitFor = async (predicate, ms = 9000) => {
            for (let waited = 0; waited < ms; waited += 500) {
                if (await predicate()) return true;
                await sleep(500);
            }
            return false;
        };
        await check('idlePool: a fresh Chrome is topped up from 1 tab to 3 idle tabs', await waitFor(async () => (await blanks()) === 3), `blank=${await blanks()}`);

        const windowCheck = await pooled.cdp();
        const windowIds = new Set();
        for (const page of await pooled.chromePages()) {
            const { result } = await windowCheck.send('Browser.getWindowForTarget', { targetId: page.id });
            windowIds.add(result?.windowId);
        }
        windowCheck.close();
        // One window per tab: Chrome hides every tab of a window but one, and a hidden tab's renderer starves.
        await check('idlePool: every idle tab has a window of its own', windowIds.size === 3 && !windowIds.has(undefined), `windows=${windowIds.size}`);

        const holders = [];
        // A tab another session has just navigated can still be listed as about:blank for a few ms;
        // the proxy refuses it (TAB_LEASED) and the session picks the next idle tab, as the prompt says.
        const claim = async () => {
            for (const page of (await pooled.chromePages()).filter((p) => p.url === 'about:blank')) {
                const cdpClient = await pooled.cdp();
                const { result } = await cdpClient.send('Target.attachToTarget', { targetId: page.id, flatten: true });
                const nav = await cdpClient.send('Page.navigate', { url: `data:text/html,held-${holders.length}` }, result.sessionId);
                if (!nav.error) { holders.push(cdpClient); return true; }
                cdpClient.close();
            }
            return false;
        };
        for (let i = 0; i < 3; i++) await claim();
        await check('idlePool: after 3 claims the pool is replenished within the cap', await waitFor(async () => (await blanks()) >= 2), `blank=${await blanks()} total=${await total()}`);
        const simultaneous = await Promise.all([claim(), claim()]);
        await check('idlePool: two simultaneous sessions each still find their own idle tab', simultaneous.every(Boolean), simultaneous.join(','));
        for (let i = 0; i < 4; i++) await claim();
        await sleep(3000);
        await check('idlePool: total tabs never exceed the cap', (await total()) <= 5, `total=${await total()}`);
        for (const holder of holders) holder.close();
        pooled.stop();
    },

    // A tab a client explicitly opens in a shared window (newWindow:false, a popup) may be in use
    // right now, so the pool must not close it for a while (BUG-DG-2026-10-12-010: it used to close
    // such tabs within milliseconds). Once such a tab has stayed blank and unleased for the grace
    // period it is a leftover: it is closed and the pool keeps one idle tab per window.
    async sharedWindowBlanksAreReplaced() {
        const graceMs = 14000;
        const pooled = new SandboxProxy(option('--proxy-dir', undefined), {
            CHROME_AGENT_MIN_IDLE_TABS: '3', CHROME_AGENT_MAX_PAGES: '8', CHROME_AGENT_ABANDON_GRACE_MS: String(graceMs),
        });
        await pooled.start();
        const cdpClient = await pooled.cdp();
        await sleep(3000);
        const sharedIds = [];
        for (let i = 0; i < 3; i++) {
            const { result } = await cdpClient.send('Target.createTarget', { url: 'about:blank', newWindow: false });
            sharedIds.push(result.targetId);
        }
        const attached = await cdpClient.send('Target.attachToTarget', { targetId: sharedIds[0], flatten: true });
        // Long enough for the previous rule to have closed it (two pool ticks), well inside the grace.
        await sleep(6500);
        const probe = await Promise.race([
            cdpClient.send('Runtime.evaluate', { expression: 'location.href', returnByValue: true }, attached.result?.sessionId),
            sleep(5000).then(() => undefined),
        ]);
        await check('sharedWindowBlanksAreReplaced: a client-created shared-window tab is still usable 6.5s after attach',
            probe?.result?.result?.value === 'about:blank', JSON.stringify(probe?.error ?? probe?.result?.result ?? 'no answer'));
        const survivors = async () => (await pooled.chromePages()).filter((p) => sharedIds.includes(p.id)).length;
        let gone = false;
        for (let waited = 0; waited < 30000 && !gone; waited += 1000) {
            gone = (await survivors()) === 0;
            if (!gone) await sleep(1000);
        }
        await check('sharedWindowBlanksAreReplaced: unused shared-window blanks are closed once the grace period is over', gone, `left=${await survivors()}`);
        const windows = new Set();
        const blanks = (await pooled.chromePages()).filter((p) => p.url === 'about:blank');
        for (const page of blanks) {
            const { result } = await cdpClient.send('Browser.getWindowForTarget', { targetId: page.id });
            windows.add(result?.windowId);
        }
        await check('sharedWindowBlanksAreReplaced: the idle tabs that remain have a window each', blanks.length >= 3 && windows.size === blanks.length, `blanks=${blanks.length} windows=${windows.size}`);
        cdpClient.close();
        pooled.stop();
    },

    // A tab a client opens (MCP new_page never asks for a window) must not land in a window that
    // already holds tabs: that makes it a hidden tab. The proxy gives it a window of its own.
    async clientTabsGetOwnWindow() {
        const mcp = proxy.mcp('W');
        await mcp.start();
        const cdpClient = await proxy.cdp();
        await mcp.tool('new_page', { url: 'about:blank' });
        await mcp.tool('new_page', { url: 'about:blank' });
        await cdpClient.send('Target.createTarget', { url: 'about:blank' });
        const pages = await proxy.chromePages();
        const windows = new Set();
        for (const page of pages) {
            const { result } = await cdpClient.send('Browser.getWindowForTarget', { targetId: page.id });
            windows.add(result?.windowId);
        }
        await check('clientTabsGetOwnWindow: every tab, including client-created ones, has its own window',
            pages.length >= 4 && windows.size === pages.length, `tabs=${pages.length} windows=${windows.size}`);
        cdpClient.close();
        mcp.stop();
    },

    // With the idle pool running, a tab a session opens with new_page must survive: it has a window
    // of its own, so the pool neither counts it as hidden nor closes it (BUG-DG-2026-10-12-010).
    async clientNewPageSurvivesPool() {
        const pooled = new SandboxProxy(option('--proxy-dir', undefined), {
            CHROME_AGENT_MIN_IDLE_TABS: '3', CHROME_AGENT_MAX_PAGES: '8',
        });
        await pooled.start();
        await sleep(3000);
        const mcp = pooled.mcp('N');
        await mcp.start();
        const created = await mcp.tool('new_page', { url: 'about:blank' });
        const pageId = Number(created.text.match(/^(\d+): \S+ \[selected\]/m)?.[1]);
        await sleep(5000);
        const probe = await mcp.tool('evaluate_script', { pageId, function: '() => location.href' });
        await check('clientNewPageSurvivesPool: the tab is still usable 5s after new_page, with the pool running',
            !created.isError && !probe.isError && probe.text.includes('about:blank'), `${created.text.slice(0, 80)} | ${probe.text.slice(0, 120)}`);
        mcp.stop();
        pooled.stop();
    },

    // Sessions use their tab without bringing it to the front. Every claimed tab must still be a
    // visible one: a hidden tab's renderer is starved under load (CDP calls hang, pages never render).
    async claimedTabsAreVisible() {
        const pooled = new SandboxProxy(option('--proxy-dir', undefined), {
            CHROME_AGENT_MIN_IDLE_TABS: '3', CHROME_AGENT_MAX_PAGES: '8',
        });
        await pooled.start();
        await sleep(4000);
        const idle = (await pooled.chromePages()).filter((p) => p.url === 'about:blank').slice(0, 3);
        const states = await Promise.all(idle.map(async (page, i) => {
            const cdpClient = await pooled.cdp();
            const { result } = await cdpClient.send('Target.attachToTarget', { targetId: page.id, flatten: true });
            await cdpClient.send('Page.navigate', { url: `data:text/html,visible-${i}` }, result.sessionId);
            const evaluated = await Promise.race([
                cdpClient.send('Runtime.evaluate', { expression: 'document.visibilityState', returnByValue: true }, result.sessionId),
                sleep(8000).then(() => undefined),
            ]);
            cdpClient.close();
            return evaluated?.result?.result?.value ?? 'no answer';
        }));
        await check('claimedTabsAreVisible: 3 concurrently claimed pool tabs are all visible', idle.length === 3 && states.every((v) => v === 'visible'), states.join(','));
        const { sharedWindowPages } = await (await fetch(`${pooled.base}/proxy/status`)).json();
        await check('claimedTabsAreVisible: /proxy/status reports no hidden shared-window tab', sharedWindowPages === 0, `sharedWindowPages=${sharedWindowPages}`);
        pooled.stop();
    },

    // A request Chrome leaves unanswered is logged while it is pending, with the host load, so a
    // "hung page" is attributable on the spot; /proxy/status exposes the count.
    async slowRequestLog() {
        const cdpClient = await proxy.cdp();
        const { result: created } = await cdpClient.send('Target.createTarget', { url: 'about:blank' });
        const { result } = await cdpClient.send('Target.attachToTarget', { targetId: created.targetId, flatten: true });
        // Never resolves, so Chrome never answers.
        void cdpClient.send('Runtime.evaluate', { expression: 'new Promise(() => {})', awaitPromise: true }, result.sessionId);
        await sleep(14500);
        const status = await (await fetch(`${proxy.base}/proxy/status`)).json();
        const logged = fs.readFileSync(proxy.logPath, 'utf8').split('\n').filter((l) => /slow request .* Runtime\.evaluate/.test(l));
        await check('slowRequestLog: an unanswered request is logged once with load', logged.length === 1 && /sess=\w{8} \[owned page [^\]]*\] unanswered/.test(logged[0]) && /load \d+ on \d+ cpus, \d+ pending, chrome up \d+m/.test(logged[0]), logged.join(' | ').slice(0, 200));
        await check('slowRequestLog: /proxy/status reports slowRequests, loadavg1 and cpus', status.slowRequests >= 1 && typeof status.loadavg1 === 'number' && status.cpus > 0, JSON.stringify({ s: status.slowRequests, l: status.loadavg1, c: status.cpus }));
        cdpClient.close();
    },
});
