/**
 * [INPUT]
 * - node_modules/next/package.json `engines.node`: the Node.js floor Next itself enforces (POS: SSOT for "usable")
 * - PATH and `<frontend>/.myrm/node/bin/node`: where a real Node.js can be found
 * - ../myrm-agent-desktop/scripts/fetch_node_runtime.py (POS: pinned, SHA-256-verified download shared with the desktop bundle)
 *
 * [OUTPUT]
 * - ensureNodeRuntime: absolute path of a real Node.js, fetching the pinned one when the machine has none
 * - nodeEnv: process env with that Node.js first on PATH
 * - `bun run scripts/node-runtime.ts ensure`: prints that path (install / setup warm-up)
 *
 * [POS]
 * The Next dev server runs on Node.js, never on Bun. Bun 1.3 does not emit `close` on a proxied
 * response when the client disconnects, so Next's rewrite proxy keeps every aborted SSE upstream
 * open, and it buffers a stalled reader without bound. Bun also injects a `node` shim that reports
 * Node.js while being Bun, so "a `node` exists on PATH" proves nothing: each candidate is executed.
 */
import { spawnSync } from 'child_process';
import fs from 'fs';
import path from 'path';

type Version = readonly [number, number, number];

export interface NodeProbe {
  version: Version;
  isBun: boolean;
}

export type ProbeNode = (candidate: string) => NodeProbe | null;

export interface ResolveOptions {
  frontendRoot: string;
  envPath: string | undefined;
  probe?: ProbeNode;
}

const PROBE_SOURCE =
  'process.stdout.write(JSON.stringify({ version: process.versions.node, bun: Boolean(process.versions.bun) }))';
const PROBE_TIMEOUT_MS = 10_000;
// The fetch script bounds each download at 900 s with retries; this only stops a wedged interpreter.
const PROVISION_TIMEOUT_MS = 30 * 60_000;
const NODE_FILE = process.platform === 'win32' ? 'node.exe' : 'node';
// nodejs.org served ~86 KB/s from a mainland-China network while this mirror served ~10 MB/s.
const MIRROR_HINT = 'https://cdn.npmmirror.com/binaries/node';

export class NodeRuntimeError extends Error {}

export function parseVersion(text: string): Version | null {
  const match = /(\d+)\.(\d+)\.(\d+)/.exec(text);
  return match ? [Number(match[1]), Number(match[2]), Number(match[3])] : null;
}

function atLeast(version: Version, floor: Version): boolean {
  for (let i = 0; i < 3; i += 1) {
    if (version[i] !== floor[i]) {
      return version[i] > floor[i];
    }
  }
  return true;
}

export function nodeFloor(frontendRoot: string): Version {
  const manifest = path.join(frontendRoot, 'node_modules', 'next', 'package.json');
  const pkg = JSON.parse(fs.readFileSync(manifest, 'utf8')) as { engines?: { node?: string } };
  const floor = parseVersion(pkg.engines?.node ?? '');
  if (!floor) {
    throw new NodeRuntimeError(`${manifest} declares no engines.node floor; run bun install first.`);
  }
  return floor;
}

export function probeNode(candidate: string): NodeProbe | null {
  const result = spawnSync(candidate, ['-e', PROBE_SOURCE], { encoding: 'utf8', timeout: PROBE_TIMEOUT_MS });
  if (result.status !== 0) {
    return null;
  }
  try {
    const parsed = JSON.parse(result.stdout) as { version: string; bun: boolean };
    const version = parseVersion(parsed.version);
    return version ? { version, isBun: parsed.bun } : null;
  } catch {
    return null;
  }
}

function isExecutableFile(file: string): boolean {
  try {
    fs.accessSync(file, fs.constants.X_OK);
    return fs.statSync(file).isFile();
  } catch {
    return false;
  }
}

export const provisionedNodeDir = (frontendRoot: string): string => path.join(frontendRoot, '.myrm', 'node', 'bin');

function candidates({ frontendRoot, envPath }: ResolveOptions): string[] {
  const dirs = [...(envPath ?? '').split(path.delimiter), provisionedNodeDir(frontendRoot)];
  const files = dirs.filter(Boolean).map((dir) => path.join(dir, NODE_FILE));
  return [...new Set(files)].filter(isExecutableFile);
}

/** First real Node.js at or above Next's floor: PATH order, then the provisioned runtime. */
export function resolveNodeRuntime(options: ResolveOptions): string | null {
  const floor = nodeFloor(options.frontendRoot);
  const probe = options.probe ?? probeNode;
  return (
    candidates(options).find((file) => {
      const found = probe(file);
      return found !== null && !found.isBun && atLeast(found.version, floor);
    }) ?? null
  );
}

function provision(frontendRoot: string): void {
  const script = path.join(frontendRoot, '..', 'myrm-agent-desktop', 'scripts', 'fetch_node_runtime.py');
  const result = spawnSync('python3', [script, '--output-dir', provisionedNodeDir(frontendRoot), '--name', 'node'], {
    stdio: 'inherit',
    timeout: PROVISION_TIMEOUT_MS,
  });
  if (result.status !== 0) {
    throw new NodeRuntimeError(
      `Fetching the pinned Node.js failed (${result.error?.message ?? `exit ${result.status}`}).`,
    );
  }
}

export function ensureNodeRuntime(options: ResolveOptions): string {
  const found = resolveNodeRuntime(options);
  if (found) {
    return found;
  }
  const floor = nodeFloor(options.frontendRoot).join('.');
  console.log(
    `No Node.js >= ${floor} on PATH (Bun's own \`node\` shim does not count) — fetching the pinned runtime` +
      ` (slow? set MYRM_NODE_DIST_URL=${MIRROR_HINT})...`,
  );
  try {
    provision(options.frontendRoot);
  } catch (error) {
    throw new NodeRuntimeError(
      `${String(error)} Install Node.js >= ${floor} from https://nodejs.org and run \`bun run dev\` again.`,
    );
  }
  const fetched = resolveNodeRuntime(options);
  if (!fetched) {
    throw new NodeRuntimeError(
      `The fetched runtime is not a usable Node.js >= ${floor}; install one from https://nodejs.org.`,
    );
  }
  return fetched;
}

/**
 * The environment Next must run in. Turbopack launches its PostCSS workers by looking `node` up on
 * PATH, so the validated Node.js has to come first or they would resolve an older one — or Bun's shim.
 */
export function nodeEnv(nodeBin: string, env: NodeJS.ProcessEnv): NodeJS.ProcessEnv {
  return { ...env, PATH: [path.dirname(nodeBin), env.PATH].filter(Boolean).join(path.delimiter) };
}

if (require.main === module && process.argv[2] === 'ensure') {
  try {
    console.log(ensureNodeRuntime({ frontendRoot: process.cwd(), envPath: process.env.PATH }));
  } catch (error) {
    console.error(`❌ ${error instanceof Error ? error.message : String(error)}`);
    process.exit(1);
  }
}
