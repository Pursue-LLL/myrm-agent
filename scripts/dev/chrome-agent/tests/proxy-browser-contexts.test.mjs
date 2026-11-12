// Proxy-level tests of browser-context ownership: a context lives exactly as long as the connection
// that created it. The proxy runs for real against a scripted stand-in for Chrome
// (tests/support/staged-proxy.mjs), so the wiring in pipe-cdp-proxy.mjs is covered: the creation
// request that outlives its client, the dispose request the proxy sends, the status counters.
// Run: node --test scripts/dev/chrome-agent/tests/
import test, { describe } from 'node:test';
import assert from 'node:assert/strict';
import { HOLD, skipReason, startProxy } from './support/staged-proxy.mjs';

const CREATE = 'Target.createBrowserContext';
const DISPOSE = 'Target.disposeBrowserContext';

/** A fresh proxy per test: ids, counters and Chrome's script stay independent. */
async function withProxy(run) {
    const proxy = await startProxy();
    let created = 0;
    proxy.chrome.on(CREATE, () => ({ browserContextId: `CTX-${++created}` }));
    try {
        await run(proxy);
    } finally {
        await proxy.stop();
    }
}

const disposedIds = (proxy) => proxy.chrome.requests(DISPOSE).map((msg) => msg.params.browserContextId);
const disposalOf = (id) => (msg) => msg.method === DISPOSE && msg.params.browserContextId === id;
const contextIdOf = async (client) => (await client.send(CREATE)).result.browserContextId;

/** Round-trip a marker so everything the proxy sent Chrome before it has been received. */
async function flush(proxy, client) {
    const marker = `flush-${Math.random()}`;
    await client.send('Runtime.evaluate', { expression: marker });
    await proxy.chrome.waitFor((msg) => msg.params?.expression === marker);
}

describe('browser contexts follow the connection that created them', { skip: skipReason }, () => {
    for (const [how, leave] of [['closes cleanly', (client) => client.close()], ['dies abruptly', (client) => client.abort()]]) {
        test(`a client that ${how} has its contexts disposed, and a bystander's are left alone`, async () => {
            await withProxy(async (proxy) => {
                const [leaver, bystander] = [await proxy.connect(), await proxy.connect()];
                const mine = [await contextIdOf(leaver), await contextIdOf(leaver)];
                const theirs = await contextIdOf(bystander);
                assert.equal((await proxy.status()).ownedBrowserContexts, 3);

                await leave(leaver);
                for (const id of mine) await proxy.chrome.waitFor(disposalOf(id));
                await flush(proxy, bystander);
                assert.deepEqual(disposedIds(proxy).sort(), mine.sort());
                assert.equal((await proxy.status()).ownedBrowserContexts, 1);

                await bystander.close();
                await proxy.chrome.waitFor(disposalOf(theirs));
                assert.equal((await proxy.status()).ownedBrowserContexts, 0);
            });
        });
    }

    test('a creation Chrome answers after its client is gone is disposed on arrival', async () => {
        await withProxy(async (proxy) => {
            proxy.chrome.on(CREATE, () => HOLD);
            const client = await proxy.connect();
            client.send(CREATE).catch(() => {});
            const request = await proxy.chrome.waitFor((msg) => msg.method === CREATE);

            await client.abort();
            await proxy.waitLogged('c1 disconnected');
            assert.deepEqual(disposedIds(proxy), []);

            proxy.chrome.reply(request.id, { browserContextId: 'CTX-LATE' });
            await proxy.chrome.waitFor(disposalOf('CTX-LATE'));
            assert.equal((await proxy.status()).ownedBrowserContexts, 0);
            assert.equal((await proxy.status()).pendingRequests, 0);
        });
    });

    test('a context its creator disposed itself is not disposed again when the creator leaves', async () => {
        await withProxy(async (proxy) => {
            const [client, observer] = [await proxy.connect(), await proxy.connect()];
            const id = await contextIdOf(client);
            const kept = await contextIdOf(client);
            await client.send(DISPOSE, { browserContextId: id });
            assert.equal((await proxy.status()).ownedBrowserContexts, 1);

            await client.close();
            await proxy.chrome.waitFor(disposalOf(kept));
            await flush(proxy, observer);
            assert.deepEqual(disposedIds(proxy), [id, kept]);
        });
    });

    test('a refused creation owns nothing and a leaving client disposes nothing', async () => {
        await withProxy(async (proxy) => {
            proxy.chrome.on(CREATE, (msg) => {
                proxy.chrome.fail(msg.id, 'refused');
                return HOLD;
            });
            const [client, observer] = [await proxy.connect(), await proxy.connect()];
            assert.equal((await client.send(CREATE)).error.message, 'refused');
            assert.equal((await proxy.status()).ownedBrowserContexts, 0);

            await client.close();
            await flush(proxy, observer);
            assert.deepEqual(disposedIds(proxy), []);
        });
    });

    test('Chrome refusing a dispose is logged and the proxy keeps serving', async () => {
        await withProxy(async (proxy) => {
            proxy.chrome.on(DISPOSE, (msg) => {
                proxy.chrome.fail(msg.id, 'Failed to find context');
                return HOLD;
            });
            const [client, observer] = [await proxy.connect(), await proxy.connect()];
            const id = await contextIdOf(client);

            await client.close();
            await proxy.waitLogged(`dispose of orphaned browser context ${id} failed: Failed to find context`);
            assert.equal((await observer.send('Runtime.evaluate', { expression: '1' })).error, undefined);
            assert.equal((await proxy.status()).chromeRunning, true);
        });
    });

    test('contexts survive other clients connecting and leaving', async () => {
        await withProxy(async (proxy) => {
            const owner = await proxy.connect();
            const id = await contextIdOf(owner);
            for (let i = 0; i < 3; i++) await (await proxy.connect()).close();
            await flush(proxy, owner);
            assert.deepEqual(disposedIds(proxy), []);
            assert.equal((await proxy.status()).ownedBrowserContexts, 1);
            await owner.close();
            await proxy.chrome.waitFor(disposalOf(id));
        });
    });
});
