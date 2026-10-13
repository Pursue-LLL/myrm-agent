/**
 * process-snapshot — what Chrome's renderer processes look like while a request is stalled.
 *
 * [INPUT]:  Chrome's pid; `ps` output (injectable for tests), sampled twice a short window apart.
 * [OUTPUT]: one log-ready line, `renderers: <pid>(id<client>) pri <n> <cpu>%cpu <state> <share>core, …`, or null.
 *           `<cpu>%cpu` is ps's decaying average; `<share>core` is the renderer's CPU time over the
 *           sample window divided by the window's wall time, so ~1 means the renderer is running flat
 *           out (its page is busy) and a value far below 1 on a renderer that `ps` shows as runnable (R)
 *           means it is waiting for a CPU the host does not give it.
 * [POS]:    request-watch asks for it when a stall is first seen, so a later "the page hung" report
 *           has the physical state of every renderer at that moment, which the request log alone
 *           cannot show.
 */
import { execFile } from 'node:child_process';
import { performance } from 'node:perf_hooks';

const PS_ARGS = ['-Ao', 'pid=,ppid=,pri=,pcpu=,stat=,time=,command='];
const ROW = /^\s*(\d+)\s+(\d+)\s+(-?\d+)\s+([\d.]+)\s+(\S+)\s+(\S+)\s+(.*)$/;
/** Long enough that a 10 ms scheduling jitter in the two `ps` launches stays within a few percent. */
const SAMPLE_WINDOW_MS = 2000;

/** ps TIME (`[dd-][hh:]mm:ss.hh`) in seconds; NaN when it does not parse. */
export function parseCpuTime(text) {
    const [days, clock] = text.includes('-') ? text.split('-') : [0, text];
    const parts = clock.split(':').map(Number);
    if (parts.length > 3 || parts.some((p) => !Number.isFinite(p))) return NaN;
    return parts.reduce((total, p) => total * 60 + p, 0) + Number(days) * 86400;
}

/** Renderer children of `chromePid` from `ps` output, keyed by pid. */
function parseRenderers(psOutput, chromePid) {
    const rows = new Map();
    for (const line of psOutput.split('\n')) {
        const m = ROW.exec(line);
        if (!m || Number(m[2]) !== chromePid || !m[7].includes('--type=renderer')) continue;
        rows.set(Number(m[1]), {
            pid: Number(m[1]),
            clientId: /--renderer-client-id=(\d+)/.exec(m[7])?.[1] ?? '?',
            pri: m[3],
            pcpu: m[4],
            state: m[5],
            cpuSeconds: parseCpuTime(m[6]),
        });
    }
    return rows;
}

/**
 * Summary of the renderers in `first`, in pid order. With `second` (a later `ps` of the same
 * processes, `windowSeconds` after the first) each renderer present in both also gets its core share.
 */
export function summarizeRenderers(first, chromePid, second = null, windowSeconds = 0) {
    const before = parseRenderers(first, chromePid);
    const after = second ? parseRenderers(second, chromePid) : new Map();
    const rows = [...before.values()].sort((a, b) => a.pid - b.pid).map((r) => {
        const later = after.get(r.pid);
        const share = later && windowSeconds > 0 ? (later.cpuSeconds - r.cpuSeconds) / windowSeconds : NaN;
        return `${r.pid}(id${r.clientId}) pri ${r.pri} ${r.pcpu}%cpu ${r.state}${Number.isFinite(share) ? ` ${share.toFixed(2)}core` : ''}`;
    });
    return rows.length ? `renderers: ${rows.join(', ')}` : null;
}

const defaultSleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/** One `ps`, resolved with its output and when it was started; null on failure. */
function runPs(exec) {
    const startedAt = performance.now();
    return new Promise((resolve) => {
        exec('ps', PS_ARGS, { timeout: 3000, maxBuffer: 8 * 1024 * 1024 }, (err, stdout) => {
            resolve(err ? null : { output: String(stdout), startedAt });
        });
    });
}

/**
 * Resolves with the summary, or null when Chrome is down or the first `ps` fails; never rejects.
 * A failing second `ps` only drops the core shares. The window is measured between the two `ps`
 * launches, which read the process table at the same point of their run.
 */
export async function snapshotRenderers(chromePid, exec = execFile, { windowMs = SAMPLE_WINDOW_MS, sleep = defaultSleep } = {}) {
    if (!chromePid) return null;
    const first = await runPs(exec);
    if (!first) return null;
    await sleep(windowMs);
    const second = await runPs(exec);
    const windowSeconds = second ? (second.startedAt - first.startedAt) / 1000 : 0;
    return summarizeRenderers(first.output, chromePid, second?.output ?? null, windowSeconds);
}
