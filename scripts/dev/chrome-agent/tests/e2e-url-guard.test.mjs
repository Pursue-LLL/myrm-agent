// Unit tests for e2e-url-guard.mjs (pure policy, no proxy or Chrome needed).
// Run: node --test scripts/dev/chrome-agent/tests/
import test from 'node:test';
import assert from 'node:assert/strict';
import { SHARED_FRONTEND_PORT } from '../dev-ports.mjs';
import { E2E_URL_REJECT_CODE, E2E_URL_REJECT_MESSAGE, createE2eUrlGuard } from '../e2e-url-guard.mjs';

const guard = createE2eUrlGuard({ allow: false });

test('the UI ports of ChromeE2E are forbidden on localhost, whatever the scheme or case', () => {
    for (const url of [
        'http://localhost:3000/',
        'https://localhost:3000/x',
        'http://127.0.0.1:3002',
        'http://LocalHost:3000/',
        `http://localhost:${SHARED_FRONTEND_PORT}/`,
    ]) {
        assert.equal(guard.isForbidden(url), true, url);
    }
});

test('other ports, other hosts and the scheme default ports are left alone', () => {
    for (const url of [
        'http://localhost:3001/',
        'http://localhost:9333/',
        'http://example.com:3000/',
        'http://localhost/',
        'https://localhost/',
        'about:blank',
        'data:text/html,hello',
    ]) {
        assert.equal(guard.isForbidden(url), false, url);
    }
});

test('anything that is not a usable URL string is not forbidden', () => {
    for (const value of [undefined, null, 3000, {}, '', '   ', 'not a url', 'http://']) {
        assert.equal(guard.isForbidden(value), false, String(value));
    }
});

test('allow lifts the guard for every URL', () => {
    const open = createE2eUrlGuard({ allow: true });
    assert.equal(open.isForbidden('http://localhost:3000/'), false);
    assert.equal(open.forbiddenNavigation({ method: 'Page.navigate', params: { url: 'http://localhost:3000/' } }), undefined);
});

test('only Page.navigate and Target.createTarget are screened, and the offending url is returned', () => {
    const url = 'http://localhost:3002/';
    assert.equal(guard.forbiddenNavigation({ method: 'Page.navigate', params: { url } }), url);
    assert.equal(guard.forbiddenNavigation({ method: 'Target.createTarget', params: { url } }), url);
    assert.equal(guard.forbiddenNavigation({ method: 'Page.reload', params: { url } }), undefined);
    assert.equal(guard.forbiddenNavigation({ method: 'Runtime.evaluate', params: { expression: url } }), undefined);
    assert.equal(guard.forbiddenNavigation({ method: 'Page.navigate' }), undefined);
    assert.equal(guard.forbiddenNavigation({ method: 'Page.navigate', params: { url: 'http://example.com/' } }), undefined);
});

test('the rejection is a CDP error reply carrying the machine-readable marker', () => {
    assert.deepEqual(guard.rejection(7), { id: 7, error: { code: E2E_URL_REJECT_CODE, message: E2E_URL_REJECT_MESSAGE } });
    assert.match(E2E_URL_REJECT_MESSAGE, /^CHROME_AGENT_E2E_URL_REJECTED: /);
});
