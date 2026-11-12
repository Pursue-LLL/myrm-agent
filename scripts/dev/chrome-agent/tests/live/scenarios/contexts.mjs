// Browser-context ownership: a context an MCP opens with `new_page { isolatedContext }` lives exactly
// as long as the connection that created it. chrome-devtools-mcp never disposes the contexts it creates
// and the proxy's Chrome outlives every client, so without ownership each one (and its renderer)
// stays resident until Chrome restarts. Ground truth is Chrome's own `Target.getBrowserContexts`,
// asked over a bare client, never the proxy's bookkeeping.
import { sleep } from '../harness.mjs';

export const contextScenarios = ({ proxy, check }) => {
    const liveContexts = async () => {
        const client = await proxy.cdp();
        try {
            return (await client.send('Target.getBrowserContexts')).result.browserContextIds;
        } finally {
            client.close();
        }
    };
    const pageCount = async () => (await proxy.chromePages()).length;
    const added = (after, before) => after.filter((id) => !before.includes(id));

    const until = async (predicate, ms = 8000) => {
        for (let waited = 0; waited < ms; waited += 250) {
            if (await predicate()) return true;
            await sleep(250);
        }
        return predicate();
    };

    /** Open `names.length` isolated contexts through `mcp`; returns the ids Chrome created for them. */
    async function openIsolated(mcp, names) {
        const before = await liveContexts();
        for (const name of names) {
            const { isError, text } = await mcp.tool('new_page', { url: 'about:blank', isolatedContext: name });
            if (isError) throw new Error(`new_page(${name}) failed: ${text.slice(0, 120)}`);
        }
        return added(await liveContexts(), before);
    }

    /** The shared shape: two isolated contexts opened, the client leaves, Chrome must be back to baseline. */
    async function releasedAfter(label, leave) {
        const mcp = proxy.mcp('A');
        await mcp.start();
        const contextsBefore = await liveContexts();
        const pagesBefore = await pageCount();
        const mine = await openIsolated(mcp, ['iso-1', 'iso-2']);
        await check(`${label}: both isolated contexts are alive while their MCP is connected`,
            mine.length === 2 && (await pageCount()) === pagesBefore + 2,
            `contexts +${mine.length} pages ${pagesBefore}->${await pageCount()}`);

        leave(mcp);
        const gone = await until(async () => (await liveContexts()).every((id) => !mine.includes(id)));
        await check(`${label}: contexts are disposed once the MCP is gone`, gone,
            `before=${contextsBefore.length} after=${(await liveContexts()).length}`);
        await check(`${label}: their pages went with them`, await until(async () => (await pageCount()) === pagesBefore),
            `pages ${pagesBefore}->${await pageCount()}`);
    }

    return {
        // An orderly exit: stdin closed, SIGTERM.
        contextsReleasedOnExit: () => releasedAfter('contextsReleasedOnExit', (mcp) => mcp.stop()),

        // A killed client never says goodbye: the proxy only sees the socket drop.
        contextsReleasedOnKill: () => releasedAfter('contextsReleasedOnKill', (mcp) => mcp.proc.kill('SIGKILL')),

        // Contexts belong to their creator: one client leaving must not touch another's.
        async contextsOfOthersSurvive() {
            const [a, b] = [proxy.mcp('A'), proxy.mcp('B')];
            await a.start(); await b.start();
            const theirs = await openIsolated(a, ['iso-a']);
            const mine = await openIsolated(b, ['iso-b']);
            await check('contextsOfOthersSurvive: each client opened one context', theirs.length === 1 && mine.length === 1);

            a.stop();
            await until(async () => (await liveContexts()).every((id) => !theirs.includes(id)));
            const alive = await liveContexts();
            await check('contextsOfOthersSurvive: the leaver\'s context is gone, the other client\'s is untouched',
                alive.includes(mine[0]) && !alive.includes(theirs[0]), `alive=${alive.length}`);
            const stillUsable = (await b.pages()).some((p) => p.url === 'about:blank');
            await check('contextsOfOthersSurvive: the other client still sees its page', stillUsable);
            b.stop();
        },
    };
};
