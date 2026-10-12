// Live regression for pipe-cdp-proxy session isolation.
//
// Spins up an isolated proxy + Chrome (random port, temp profile) and drives real
// chrome-devtools-mcp processes. Invariant under test: whatever other clients do
// (start, stop, attach, detach, exit), every live MCP's list_pages equals Chrome's
// real page set.
//
//   node tests/live-regression.mjs [--only t1,t2b] [--rounds 20] [--proxy-dir <dir>]
//
// --proxy-dir points at a directory holding another pipe-cdp-proxy.mjs (+ node_modules/ws),
// e.g. the pre-fix proxy: the isolation scenarios must then FAIL (negative control).
//
// Scenarios live in tests/live/scenarios/*.mjs; each exports a factory taking the shared
// context from tests/live/context.mjs and returning { name: async () => {...} }.
import { createContext } from './live/context.mjs';
import { findMcpEntry } from './live/harness.mjs';
import { isolationScenarios } from './live/scenarios/isolation.mjs';
import { tabScenarios } from './live/scenarios/tabs.mjs';
import { visibilityScenarios } from './live/scenarios/visibility.mjs';

const argv = process.argv.slice(2);
const option = (name, fallback) => {
    const i = argv.indexOf(name);
    return i >= 0 ? argv[i + 1] : fallback;
};
const only = option('--only', '')?.split(',').filter(Boolean);

if (!findMcpEntry()) {
    console.log('SKIP: chrome-devtools-mcp not installed (npx chrome-devtools-mcp once, or set CHROME_DEVTOOLS_MCP_JS)');
    process.exit(0);
}

const ctx = createContext(option);
const { proxy, results, check } = ctx;
const scenarios = { ...isolationScenarios(ctx), ...visibilityScenarios(ctx), ...tabScenarios(ctx) };

await proxy.start();
console.log(`sandbox proxy on ${proxy.base} (log: ${proxy.logPath})`);
const selected = only?.length ? only : Object.keys(scenarios);
for (const name of selected) {
    console.log(`\n[${name}]`);
    try {
        await proxy.resetPages(3);
        await scenarios[name]();
    } catch (err) {
        await check(`${name}: scenario completed`, false, err.message);
    }
}
const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
if (failed.length) console.log(`FAILED:\n${failed.map((r) => `  - ${r.label} ${r.detail}`).join('\n')}`);
proxy.stop({ keepLog: failed.length > 0 });
process.exit(failed.length ? 1 : 0);
