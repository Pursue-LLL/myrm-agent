// Shared fixtures of the live regression scenarios: the sandbox proxy, the check ledger and the
// multi-client helpers every scenario file builds on.
import { SandboxProxy } from './harness.mjs';

export function createContext(option) {
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

    return {
        proxy, results, check, expectConsistent, bareAttach, option,
        ROUNDS: Number(option('--rounds', '8')),
        SETTLE_MS: 1500,
    };
}
