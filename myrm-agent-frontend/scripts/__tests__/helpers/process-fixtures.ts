import { spawn, type ChildProcess } from 'child_process';
import net from 'net';

const children: ChildProcess[] = [];

export function freePort(): Promise<number> {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address() as net.AddressInfo;
      server.close(() => resolve(port));
    });
  });
}

/** Env of a process that carries `namespace`'s dev stamp, or none at all. */
function envFor(namespace: string | null): NodeJS.ProcessEnv {
  const env = { ...process.env };
  delete env.MYRM_RUNTIME_NAMESPACE;
  delete env.MYRM_DEV_STATE_DIR;
  return namespace ? { ...env, MYRM_RUNTIME_NAMESPACE: namespace, MYRM_DEV_STATE_DIR: `/tmp/${namespace}` } : env;
}

/**
 * A real node process (not /bin/sleep: macOS hides the environment of platform binaries from
 * `ps eww`) carrying `namespace`'s dev stamp, or none, with `argv` visible in its command line.
 * Resolves once `code` printed `ready`, or after a short settle when it prints nothing.
 */
export async function startProcess(
  code: string,
  argv: string[],
  namespace: string | null,
  { printsReady = true, shellNote }: { printsReady?: boolean; shellNote?: string } = {},
): Promise<ChildProcess> {
  // With a `shellNote` the process runs under a shell (kept as its parent by the trailing `true`)
  // whose own command line carries the note.
  const [command, args] = shellNote
    ? ['/bin/sh', ['-c', `"$0" "$@"; true # ${shellNote}`, process.execPath, '-e', code, ...argv]]
    : [process.execPath, ['-e', code, ...argv]];
  const child = spawn(command, args, {
    env: envFor(namespace),
    stdio: ['ignore', 'pipe', 'ignore'],
    detached: true,
  });
  children.push(child);
  if (printsReady) {
    await new Promise<void>((resolve) => child.stdout?.once('data', () => resolve()));
  } else {
    await new Promise((resolve) => setTimeout(resolve, 400));
  }
  return child;
}

export function stopAllProcesses(): void {
  for (const child of children.splice(0)) {
    try {
      process.kill(-(child.pid as number), 'SIGKILL');
    } catch {
      // already gone
    }
  }
}

export function isAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

/** Resolves true when `child` has exited (or does so within `waitMs`); false when it is still running. */
export async function exitsWithin(child: ChildProcess, waitMs: number): Promise<boolean> {
  if (child.exitCode !== null || child.signalCode !== null) {
    return true;
  }
  return Promise.race([
    new Promise<boolean>((resolve) => child.once('exit', () => resolve(true))),
    new Promise<boolean>((resolve) => setTimeout(() => resolve(false), waitMs)),
  ]);
}
