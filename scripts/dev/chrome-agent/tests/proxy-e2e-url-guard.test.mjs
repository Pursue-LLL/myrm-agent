// Proxy-level tests of the E2E URL guard: ChromeAgent :9410 is for Agent tasks, so navigations to the
// UI ports that belong to ChromeE2E are refused over the WebSocket and over the HTTP open route alike.
// The proxy runs for real against a scripted stand-in for Chrome (tests/support/staged-proxy.mjs).
// Run: node --test scripts/dev/chrome-agent/tests/
import test, { after, before, describe } from 'node:test';
import assert from 'node:assert/strict';
import { SHARED_FRONTEND_PORT } from '../../lib/dev-ports.mjs';
import { skipReason, startProxy } from './support/staged-proxy.mjs';

const REJECT_CODE = -32001;
const REJECT_MESSAGE =
    'CHROME_AGENT_E2E_URL_REJECTED: ChromeAgent :9410 is for Agent tasks (e.g. URL extraction) only; '
    + 'chrome_e2e must use ./myrm-dev test harness → ChromeE2E :9333';
const NAVIGATING = ['Page.navigate', 'Target.createTarget'];

const FORBIDDEN = [
    'http://localhost:3000/',
    'http://127.0.0.1:3002/path?q=1',
    'http://LOCALHOST:3000',
    `http://localhost:${SHARED_FRONTEND_PORT}/`,
    'https://localhost:3000/',
];
// Ports and hosts the guard must leave alone, including the scheme defaults 80 / 443.
const ALLOWED = [
    'http://localhost:3001/',
    'http://localhost:9333/',
    'http://example.com:3000/',
    'http://localhost/',
    'https://localhost/',
    'about:blank',
    'data:text/html,hello',
    'not a url',
];

describe('E2E URL guard over the WebSocket', { skip: skipReason }, () => {
    let proxy;
    let client;
    let markers = 0;

    before(async () => {
        proxy = await startProxy();
        client = await proxy.connect();
    });
    after(async () => {
        await client?.close();
        await proxy?.stop();
    });

    /** What Chrome received for `method` and `url`, read after a marker that travels the same pipe behind it. */
    async function reachedChrome(method, url) {
        const marker = `marker-${++markers}`;
        await client.send('Runtime.evaluate', { expression: marker });
        await proxy.chrome.waitFor((msg) => msg.params?.expression === marker);
        return proxy.chrome.received.filter((msg) => msg.method === method && msg.params?.url === url);
    }

    for (const method of NAVIGATING) {
        for (const url of FORBIDDEN) {
            test(`${method} to ${url} is rejected and never reaches Chrome`, async () => {
                const reply = await client.send(method, { url });
                assert.deepEqual(reply.error, { code: REJECT_CODE, message: REJECT_MESSAGE });
                assert.equal(reply.result, undefined);
                assert.deepEqual(await reachedChrome(method, url), []);
            });
        }
        for (const url of ALLOWED) {
            test(`${method} to ${url} is forwarded and answered by Chrome`, async () => {
                const reply = await client.send(method, { url });
                assert.equal(reply.error, undefined);
                assert.equal((await reachedChrome(method, url)).length, 1);
            });
        }
    }

    test('only navigations are screened: a script that mentions a forbidden URL passes', async () => {
        const expression = 'fetch("http://localhost:3000/")';
        const reply = await client.send('Runtime.evaluate', { expression });
        assert.equal(reply.error, undefined);
        await proxy.chrome.waitFor((msg) => msg.params?.expression === expression);
    });

    test('a navigation without url, or with a non-string url, is forwarded', async () => {
        for (const params of [{}, { url: 3000 }, { url: '' }, { url: '   ' }]) {
            const reply = await client.send('Page.navigate', params);
            assert.equal(reply.error, undefined, JSON.stringify(params));
        }
    });

    test('the rejection is logged with the method and the url', async () => {
        await client.send('Page.navigate', { url: 'http://localhost:3002/logged' });
        await proxy.waitLogged('Rejected E2E URL on ChromeAgent (Page.navigate): http://localhost:3002/logged');
    });

    test('a forbidden navigation sent without an id is dropped silently: no reply, no log, no forwarding', async () => {
        const url = 'http://localhost:3000/no-id';
        client.notify('Page.navigate', { url });
        assert.deepEqual(await reachedChrome('Page.navigate', url), []);
        assert.equal(proxy.logged(`Page.navigate): ${url}`), false);
        assert.equal(client.events.length, 0);
    });
});

describe('E2E URL guard over the HTTP open route', { skip: skipReason }, () => {
    let proxy;

    before(async () => {
        proxy = await startProxy();
        proxy.chrome.on('Target.createTarget', () => ({ targetId: 'T-open' }));
    });
    after(() => proxy?.stop());

    test('a forbidden url is refused with 403 and the same message, and never reaches Chrome', async () => {
        const response = await proxy.get(`/proxy/open?url=${encodeURIComponent('http://localhost:3000/')}`);
        assert.equal(response.status, 403);
        assert.deepEqual(await response.json(), { error: REJECT_MESSAGE });
        assert.equal(proxy.chrome.requests('Target.createTarget').length, 0);
    });

    test('an allowed url opens a target through Chrome', async () => {
        const response = await proxy.get(`/proxy/open?url=${encodeURIComponent('http://example.com/')}`);
        assert.equal(response.status, 200);
        assert.deepEqual(await response.json(), { targetId: 'T-open' });
        assert.deepEqual(proxy.chrome.requests('Target.createTarget').map((msg) => msg.params), [
            { url: 'http://example.com/' },
        ]);
    });

    test('a missing url opens about:blank', async () => {
        assert.equal((await proxy.get('/proxy/open')).status, 200);
        assert.equal(proxy.chrome.requests('Target.createTarget').at(-1).params.url, 'about:blank');
    });
});

describe('E2E URL guard policy switch', { skip: skipReason }, () => {
    async function withPolicy(value, run) {
        const proxy = await startProxy({ env: { MYRM_CHROME_AGENT_ALLOW_E2E_URLS: value } });
        try {
            await run(proxy, await proxy.connect());
        } finally {
            await proxy.stop();
        }
    }

    test('MYRM_CHROME_AGENT_ALLOW_E2E_URLS=1 lets E2E urls through on both routes', async () => {
        await withPolicy('1', async (proxy, client) => {
            const url = 'http://localhost:3000/';
            assert.equal((await client.send('Page.navigate', { url })).error, undefined);
            assert.equal((await proxy.get(`/proxy/open?url=${encodeURIComponent(url)}`)).status, 200);
            assert.equal(proxy.chrome.requests('Page.navigate').length, 1);
            await client.close();
        });
    });

    test('any other value keeps the guard on', async () => {
        await withPolicy('true', async (proxy, client) => {
            const reply = await client.send('Page.navigate', { url: 'http://localhost:3000/' });
            assert.equal(reply.error?.code, REJECT_CODE);
            await client.close();
        });
    });
});
