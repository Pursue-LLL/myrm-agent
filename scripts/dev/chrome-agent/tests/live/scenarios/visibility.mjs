// What a client can see and do on pages and frames it did not create itself: late joiners,
// cross-site iframes, popups, dialogs.
import http from 'node:http';
import { sleep } from '../harness.mjs';

export const visibilityScenarios = ({ proxy, check, expectConsistent }) => ({

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

    // Content of cross-site iframes (out-of-process frames) must be visible to every client,
    // including one that joins after the frame already exists (second MCP, restarted MCP).
    async oopifVisibility() {
        const frameServer = http.createServer((_, res) => { res.setHeader('content-type', 'text/html'); res.end('<p>OOPIF-INNER-TEXT</p>'); });
        await new Promise((r) => frameServer.listen(0, '127.0.0.1', r));
        const pageServer = http.createServer((_, res) => {
            res.setHeader('content-type', 'text/html');
            res.end(`<h1>HOST-TEXT</h1><iframe src="http://localhost:${frameServer.address().port}/"></iframe>`);
        });
        await new Promise((r) => pageServer.listen(0, '127.0.0.1', r));
        const url = `http://127.0.0.1:${pageServer.address().port}/`;
        const sees = async (mcp, pageId) => (await mcp.tool('take_snapshot', { pageId })).text.includes('OOPIF-INNER-TEXT');
        const open = async (mcp, pageId) => {
            await mcp.tool('select_page', { pageId });
            await mcp.tool('navigate_page', { pageId, type: 'url', url });
            await sleep(2000);
        };

        const b = proxy.mcp('B'); await b.start();
        const [first, second] = await b.pages();
        await open(b, first.id);
        await check('oopifVisibility: owner sees the iframe content', await sees(b, first.id));
        const d = proxy.mcp('D'); await d.start(); await d.pages();
        await check('oopifVisibility: late client sees the iframe content of an existing page', await sees(d, first.id));
        await check('oopifVisibility: owner still sees the iframe content after a client joined late', await sees(b, first.id));
        await open(d, second.id);
        await check('oopifVisibility: client sees the iframe content of the page it navigated', await sees(d, second.id));
        await check('oopifVisibility: earlier client sees the iframe content of the later client\'s page', await sees(b, second.id));
        b.stop(); await sleep(1500);
        const f = proxy.mcp('F'); await f.start(); await f.pages();
        await check('oopifVisibility: restarted client sees the iframe content of both pages', (await sees(f, first.id)) && (await sees(f, second.id)));
        d.stop(); f.stop(); frameServer.close(); pageServer.close();
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
});
