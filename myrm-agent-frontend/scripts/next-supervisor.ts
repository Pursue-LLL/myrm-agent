/**
 * [INPUT]
 * - spawnChild: starts one Next.js dev server process (POS: owned by dev.ts, which knows the runtime and args)
 * - probe: physical-memory verdict for a process tree (POS: `python -m frontend_lifecycle footprint`, the SSOT for the limit)
 *
 * [OUTPUT]
 * - superviseNext: keeps one Next child alive and replaces it when its process tree outgrows the memory limit
 * - footprintProbe: the probe backed by the frontend_lifecycle CLI
 * - `FOOTPRINT*` log lines (counted by `frontend_lifecycle report`)
 *
 * [POS]
 * Turbopack keeps the compiled module graph in memory, so a long-lived dev server only ever grows (one
 * server's process tree measured 22 GB of physical footprint, enough to page the whole machine). The guard
 * bounds that growth. A restart drops the module graph and the routes that were served compile again, so it
 * is rate-limited: after `breaker.max` restarts inside `breaker.windowMs` the guard stops and says so,
 * leaving a server that is merely heavy running.
 */
import { type ChildProcess, execFile } from 'child_process';
import path from 'path';

export type FootprintVerdict = 'ok' | 'exceeded' | 'unmeasurable';

export interface FootprintReading {
  verdict: FootprintVerdict;
  /** The `FOOTPRINT pid=… mb=… limit_mb=…` line, empty when unmeasurable. */
  line: string;
}

export type FootprintProbe = (pid: number) => Promise<FootprintReading>;

export interface SuperviseOptions {
  spawnChild: () => ChildProcess;
  /** Runs between the old child exiting and the new one starting (free the port, reset shared config). */
  beforeRespawn: () => void;
  probe: FootprintProbe;
  /** The child ended without the guard asking for it. */
  onExit: (code: number | null) => void;
  onSpawnError: (error: Error) => void;
  intervalMs: number;
  breaker: { max: number; windowMs: number };
  killGraceMs?: number;
  now?: () => number;
  log?: (message: string) => void;
}

export interface NextSupervisor {
  readonly child: ChildProcess;
  /** No further sampling or respawning; the current child is left for the caller to end. */
  stop: () => void;
}

const UNMEASURABLE_LIMIT = 3;
const LOG_EVERY_SAMPLES = 10;
const EXIT_EXCEEDED = 12;
const PROBE_TIMEOUT_MS = 30_000;

export function superviseNext(options: SuperviseOptions): NextSupervisor {
  const now = options.now ?? Date.now;
  const log = options.log ?? ((message: string) => console.log(message));
  const killGraceMs = options.killGraceMs ?? 15_000;
  const restartTimes: number[] = [];
  let current: ChildProcess;
  let stopped = false;
  let restarting = false;
  let timer: NodeJS.Timeout | undefined;
  let unmeasurable = 0;
  let samples = 0;

  const start = (): ChildProcess => {
    const child = options.spawnChild();
    child.on('error', options.onSpawnError);
    child.on('exit', (code) => {
      if (child !== current) {
        return;
      }
      if (restarting && !stopped) {
        restarting = false;
        options.beforeRespawn();
        current = start();
        schedule();
        return;
      }
      stopped = true;
      clearTimeout(timer);
      options.onExit(code);
    });
    return child;
  };

  const terminate = (child: ChildProcess): void => {
    child.kill('SIGTERM');
    const force = setTimeout(() => child.kill('SIGKILL'), killGraceMs);
    force.unref();
    child.once('exit', () => clearTimeout(force));
  };

  const breakerAllows = (): boolean => {
    const cutoff = now() - options.breaker.windowMs;
    while (restartTimes.length > 0 && restartTimes[0] < cutoff) {
      restartTimes.shift();
    }
    return restartTimes.length < options.breaker.max;
  };

  const sample = async (): Promise<void> => {
    const target = current;
    const reading = target.pid === undefined ? null : await options.probe(target.pid);
    if (stopped || target !== current || reading === null) {
      schedule();
      return;
    }
    if (reading.verdict === 'unmeasurable') {
      unmeasurable += 1;
      if (unmeasurable >= UNMEASURABLE_LIMIT) {
        log(`FOOTPRINT_GUARD_OFF: memory of pid ${target.pid} could not be measured ${UNMEASURABLE_LIMIT}x in a row`);
        return;
      }
      schedule();
      return;
    }
    unmeasurable = 0;
    samples += 1;
    if (reading.verdict === 'ok') {
      if (samples === 1 || samples % LOG_EVERY_SAMPLES === 0) {
        log(reading.line);
      }
      schedule();
      return;
    }
    if (!breakerAllows()) {
      log(`FOOTPRINT_BREAKER_OPEN: ${reading.line} — ${options.breaker.max} restarts in the window, guard stopped`);
      return;
    }
    restartTimes.push(now());
    restarting = true;
    log(`FOOTPRINT_RESTART: ${reading.line} — restarting Next.js to release memory`);
    terminate(target);
  };

  const schedule = (): void => {
    if (stopped) {
      return;
    }
    timer = setTimeout(() => void sample(), options.intervalMs);
    timer.unref();
  };

  current = start();
  schedule();

  return {
    get child() {
      return current;
    },
    stop: () => {
      stopped = true;
      clearTimeout(timer);
    },
  };
}

export interface FootprintProbeOptions {
  /** Directory holding the `frontend_lifecycle` package. */
  libDir: string;
  /** Needs Python >= 3.11 (dev_gate.contract uses StrEnum); an older interpreter reads as unmeasurable. */
  python: string;
  env?: NodeJS.ProcessEnv;
}

/** Probe backed by `python -m frontend_lifecycle footprint`. */
export function footprintProbe({ libDir, python, env = process.env }: FootprintProbeOptions): FootprintProbe {
  const pythonPath = [libDir, env.PYTHONPATH].filter(Boolean).join(path.delimiter);
  return (pid) =>
    new Promise((resolve) => {
      execFile(
        python,
        ['-m', 'frontend_lifecycle', 'footprint', '--pid', String(pid)],
        { env: { ...env, PYTHONPATH: pythonPath }, timeout: PROBE_TIMEOUT_MS, encoding: 'utf8' },
        (error, stdout) => {
          // A non-zero exit sets `code` to the exit status; a spawn failure sets it to a string like ENOENT.
          const code = error === null ? 0 : (error as { code?: number | string }).code;
          if (code === 0) {
            resolve({ verdict: 'ok', line: stdout.trim() });
          } else if (code === EXIT_EXCEEDED) {
            resolve({ verdict: 'exceeded', line: stdout.trim() });
          } else {
            resolve({ verdict: 'unmeasurable', line: '' });
          }
        },
      );
    });
}
