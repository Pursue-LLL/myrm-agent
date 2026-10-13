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
    // "hung page" is attributable on the spot, with the renderers' priority and CPU share at that moment;
    // /proxy/status exposes the count.
    async slowRequestLog() {
        const cdpClient = await proxy.cdp();
        const { result: created } = await cdpClient.send('Target.createTarget', { url: 'about:blank' });
        const { result } = await cdpClient.send('Target.attachToTarget', { targetId: created.targetId, flatten: true });
        // A synchronous endless loop hangs the renderer, so Chrome never answers (an awaitPromise request would
        // be a script wait, not a stall: see scriptWaitIsNotAStall).
        void cdpClient.send('Runtime.evaluate', { expression: 'while (true) {}' }, result.sessionId);
        await sleep(14500);
        const status = await (await fetch(`${proxy.base}/proxy/status`)).json();
        const logged = fs.readFileSync(proxy.logPath, 'utf8').split('\n').filter((l) => /slow request .* Runtime\.evaluate/.test(l));
        await check('slowRequestLog: an unanswered request is logged once with load', logged.length === 1 && /sess=\w{8} \[owned page [^\]]*\] unanswered/.test(logged[0]) && /load \d+ on \d+ cpus, \d+ pending, chrome up \d+m/.test(logged[0]), logged.join(' | ').slice(0, 200));
        const snapshot = fs.readFileSync(proxy.logPath, 'utf8').split('\n').filter((l) => /stall snapshot renderers: \d+\(id\d+\) pri -?\d+ [\d.]+%cpu/.test(l));
        await check('slowRequestLog: the stall also logs the renderer processes (priority, cpu share) once', snapshot.length === 1, snapshot.join(' | ').slice(0, 220));
        await check('slowRequestLog: /proxy/status reports slowRequests, loadavg1 and cpus', status.slowRequests >= 1 && typeof status.loadavg1 === 'number' && status.cpus > 0, JSON.stringify({ s: status.slowRequests, l: status.loadavg1, c: status.cpus }));
        cdpClient.close();
    },

    // A request that waits for a page script (awaitPromise) is unanswered by design for as long as the script runs:
    // it is logged as a script wait and counted apart, never as a slow request, and takes no renderer snapshot.
    async scriptWaitIsNotAStall() {
        const before = await (await fetch(`${proxy.base}/proxy/status`)).json();
        const cdpClient = await proxy.cdp();
        const { result: created } = await cdpClient.send('Target.createTarget', { url: 'about:blank' });
        const { result } = await cdpClient.send('Target.attachToTarget', { targetId: created.targetId, flatten: true });
        const answered = await cdpClient.send('Runtime.evaluate',
            { expression: 'new Promise((r) => setTimeout(() => r("done"), 13000))', awaitPromise: true, returnByValue: true }, result.sessionId);
        const status = await (await fetch(`${proxy.base}/proxy/status`)).json();
        const lines = fs.readFileSync(proxy.logPath, 'utf8').split('\n');
        const waits = lines.filter((l) => /script wait .* Runtime\.evaluate \(awaitPromise\) still running after \d+s/.test(l));
        await check('scriptWaitIsNotAStall: the script result still reaches the client', answered?.result?.result?.value === 'done', JSON.stringify(answered?.result?.result));
        await check('scriptWaitIsNotAStall: a 13 s awaitPromise is logged as one script wait', waits.length === 1, waits.join(' | ').slice(0, 200));
        await check('scriptWaitIsNotAStall: it is not counted as a slow request', status.slowRequests === before.slowRequests && status.scriptWaits === 1, JSON.stringify({ before: before.slowRequests, now: status.slowRequests, waits: status.scriptWaits }));
        cdpClient.close();
    },

    // A page whose renderer is hung must not hold a session for longer than the reaper plus one probe
    // (the 651 s stall): the proxy closes it, fails its pending requests at once and frees its lease.
    // A page that is only waiting on a call that never completes (renderer alive) is left alone.
    // Thresholds are shortened through the environment: reap after 6 s, probe for 4 s.
    async hungPageIsClosed() {
        const guarded = new SandboxProxy(option('--proxy-dir', undefined), {
            CHROME_AGENT_HANG_REQUEST_MS: '6000', CHROME_AGENT_HANG_PROBE_MS: '4000', CHROME_AGENT_HANG_SWEEP_MS: '1000',
        });
        await guarded.start();
        const cdpClient = await guarded.cdp();
        const open = async (marker) => {
            const { result: created } = await cdpClient.send('Target.createTarget', { url: 'about:blank' });
            const { result } = await cdpClient.send('Target.attachToTarget', { targetId: created.targetId, flatten: true });
            await cdpClient.send('Page.navigate', { url: `data:text/html,${marker}` }, result.sessionId);
            return { targetId: created.targetId, sessionId: result.sessionId };
        };
        const hung = await open('hung');
        const waiting = await open('waiting');
        const healthy = await open('healthy');
        await sleep(1000);
        const reply = (promise) => Promise.race([promise, sleep(30000).then(() => ({ error: { message: 'no reply in 30s' } }))]);
        const evaluate = (page, expression, extra = {}) => reply(cdpClient.send('Runtime.evaluate', { expression, returnByValue: true, ...extra }, page.sessionId));
        const spin = evaluate(hung, 'while(true){}');
        const stuck = evaluate(waiting, 'new Promise(() => {})', { awaitPromise: true });
        await sleep(7000);
        // Sent while the guard is still probing: it must fail at once when the page is closed, not wait for the reaper.
        const follow = evaluate(hung, '1');
        const listed = async (page) => (await guarded.chromePages()).some((p) => p.id === page.targetId);
        let closed = false;
        for (let waited = 0; waited < 25000 && !closed; waited += 500) {
            closed = !(await listed(hung));
            if (!closed) await sleep(500);
        }
        await check('hungPageIsClosed: a page whose renderer spins is closed within seconds of its request timing out', closed);
        await check('hungPageIsClosed: the request that exposed the hang got the timeout reply', /timeout \(6s\)/.test((await spin).error?.message ?? ''), JSON.stringify((await spin).error));
        await check('hungPageIsClosed: a request sent meanwhile fails at once with PAGE_HUNG', /^PAGE_HUNG/.test((await follow).error?.message ?? ''), JSON.stringify((await follow).error));
        await check('hungPageIsClosed: a page that merely waits on a long call is not closed', (await listed(waiting)) && (await stuck).error?.message?.includes('timeout (6s)'), JSON.stringify((await stuck).error));
        const alive = await Promise.all([evaluate(waiting, '1+1'), evaluate(healthy, '1+1')]);
        await check('hungPageIsClosed: the waiting and the healthy page still answer', alive.every((a) => a.result?.result?.value === 2), JSON.stringify(alive.map((a) => a.result?.result ?? a.error)));
        const status = await guarded.status();
        await check('hungPageIsClosed: status counts one closed page, one answered probe, no pending request, two leases left',
            status.hungPagesClosed === 1 && status.hangProbesAnswered >= 1 && status.pendingRequests === 0 && status.leasedTabs === 2,
            JSON.stringify({ closed: status.hungPagesClosed, answered: status.hangProbesAnswered, pending: status.pendingRequests, leases: status.leasedTabs }));
        const lines = fs.readFileSync(guarded.logPath, 'utf8').split('\n').filter((l) => l.includes('hang guard:'));
        await check('hungPageIsClosed: the log names the closed page once', lines.filter((l) => /closed hung page \w{8} \(data:text\/html,hung\)/.test(l)).length === 1, lines.join(' | ').slice(0, 300));
        cdpClient.close();
        guarded.stop();
    },
});
