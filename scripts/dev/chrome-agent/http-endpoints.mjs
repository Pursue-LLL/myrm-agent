/**
 * http-endpoints — Chrome-compatible discovery endpoints and proxy admin routes.
 *
 * `/json/version` and `/json/list` mimic Chrome so `chrome-devtools-mcp --browserUrl`
 * can bootstrap against the proxy. `/json/list` asks Chrome live (Target.getTargets);
 * it never reflects the proxy's caches.
 */

import http from 'http';

/** Normalize CDP discovery paths for Playwright/Patchright (trailing slash tolerant). */
function normalizeDiscoveryPath(rawUrl) {
    if (!rawUrl) return '';
    const pathOnly = rawUrl.split('?')[0].replace(/\/+$/, '') || '/';
    return pathOnly.toLowerCase();
}

/**
 * @param {object} deps
 * @param {number} deps.port
 * @param {() => boolean} deps.chromeUp
 * @param {(method: string, params?: object) => Promise<object>} deps.cdpRequest
 * @param {() => object} deps.status  payload for /proxy/status
 * @param {(url: string) => boolean} deps.isForbiddenUrl
 * @param {string} deps.forbiddenUrlMessage
 */
export function createHttpServer({ port, chromeUp, cdpRequest, status, isForbiddenUrl, forbiddenUrlMessage }) {
    return http.createServer(async (req, res) => {
        try {
            const discoveryPath = normalizeDiscoveryPath(req.url);
            if (discoveryPath === '/json/version') {
                let version = {};
                if (chromeUp()) {
                    try {
                        version = (await cdpRequest('Browser.getVersion')).result || {};
                    } catch (e) { /* fall through with empty */ }
                }
                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({
                    Browser: version.product || 'Chrome (via Pipe CDP Proxy)',
                    'Protocol-Version': version.protocolVersion || '1.3',
                    'User-Agent': version.userAgent || '',
                    'V8-Version': version.jsVersion || '',
                    'WebKit-Version': version.product || '',
                    webSocketDebuggerUrl: `ws://127.0.0.1:${port}/devtools/browser/proxy`,
                }));
                return;
            }

            if (discoveryPath === '/json/list' || discoveryPath === '/json') {
                if (!chromeUp()) {
                    res.writeHead(503);
                    res.end('Chrome not running');
                    return;
                }
                try {
                    const result = await cdpRequest('Target.getTargets');
                    const targets = (result.result?.targetInfos || []).map((t) => ({
                        ...t,
                        id: t.targetId,
                        description: '',
                        devtoolsFrontendUrl: '',
                        webSocketDebuggerUrl: `ws://127.0.0.1:${port}/devtools/page/${t.targetId}`,
                    }));
                    res.writeHead(200, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify(targets));
                } catch (e) {
                    res.writeHead(500);
                    res.end(e.message);
                }
                return;
            }

            if (req.url === '/proxy/status') {
                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify(status(), null, 2));
                return;
            }

            if (req.url?.startsWith('/proxy/open')) {
                await handleOpen(req, res);
                return;
            }

            res.writeHead(404);
            res.end('Not found');
        } catch (e) {
            res.writeHead(500);
            res.end(e.message);
        }
    });

    async function handleOpen(req, res) {
        if (!chromeUp()) {
            res.writeHead(503);
            res.end('Chrome not running');
            return;
        }
        const parsed = new URL(req.url, `http://127.0.0.1:${port}`);
        const openUrl = parsed.searchParams.get('url') || 'about:blank';
        if (isForbiddenUrl(openUrl)) {
            res.writeHead(403, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: forbiddenUrlMessage }));
            return;
        }
        const activate = parsed.searchParams.get('activate') === '1';
        try {
            const result = await cdpRequest('Target.createTarget', { url: openUrl });
            if (activate && result.result?.targetId) {
                try {
                    await cdpRequest('Target.activateTarget', { targetId: result.result.targetId });
                } catch (e) {
                    console.error('[Proxy] Target.activateTarget failed:', e.message);
                }
            }
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify(result.result || {}));
        } catch (e) {
            res.writeHead(500);
            res.end(e.message);
        }
    }
}
