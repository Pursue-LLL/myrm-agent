/**
 * process-snapshot — what Chrome's renderer processes look like while a request is stalled.
 *
 * [INPUT]:  Chrome's pid; `ps` output (injectable for tests).
 * [OUTPUT]: one log-ready line, `renderers: <pid>(id<client>) pri <n> <cpu>%cpu <state>, …`, or null.
 * [POS]:    request-watch asks for it when a stall is first seen, so a later "the page hung" report
 *           has the physical state of every renderer at that moment (scheduling priority and CPU
 *           share), which the request log alone cannot show.
 */
import { execFile } from 'node:child_process';

const PS_ARGS = ['-Ao', 'pid=,ppid=,pri=,pcpu=,stat=,command='];
const ROW = /^\s*(\d+)\s+(\d+)\s+(-?\d+)\s+([\d.]+)\s+(\S+)\s+(.*)$/;

/** Renderer children of `chromePid` from `ps` output, in pid order. */
export function summarizeRenderers(psOutput, chromePid) {
    const rows = [];
    for (const line of psOutput.split('\n')) {
        const m = ROW.exec(line);
        if (!m || Number(m[2]) !== chromePid || !m[6].includes('--type=renderer')) continue;
        const clientId = /--renderer-client-id=(\d+)/.exec(m[6])?.[1] ?? '?';
        rows.push({ pid: Number(m[1]), text: `${m[1]}(id${clientId}) pri ${m[3]} ${m[4]}%cpu ${m[5]}` });
    }
    rows.sort((a, b) => a.pid - b.pid);
    return rows.length ? `renderers: ${rows.map((r) => r.text).join(', ')}` : null;
}

/** Resolves with the summary, or null when Chrome is down or `ps` fails; never rejects. */
export function snapshotRenderers(chromePid, exec = execFile) {
    return new Promise((resolve) => {
        if (!chromePid) return resolve(null);
        exec('ps', PS_ARGS, { timeout: 3000, maxBuffer: 8 * 1024 * 1024 }, (err, stdout) => {
            resolve(err ? null : summarizeRenderers(String(stdout), chromePid));
        });
    });
}
