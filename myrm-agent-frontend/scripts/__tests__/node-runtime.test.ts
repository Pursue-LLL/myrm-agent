// @vitest-environment node
import { spawnSync } from 'child_process';
import fs from 'fs';
import os from 'os';
import path from 'path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import {
  ensureNodeRuntime,
  nodeEnv,
  NodeRuntimeError,
  parseVersion,
  probeNode,
  provisionedNodeDir,
  resolveNodeRuntime,
  type NodeProbe,
  type ProbeNode,
} from '../node-runtime';

const NODE_FILE = process.platform === 'win32' ? 'node.exe' : 'node';
let root: string;

/** A frontend checkout whose Next declares `floor` as its Node.js requirement. */
function makeFrontend(floor = '>=20.9.0'): string {
  const frontend = path.join(root, 'myrm-agent', 'myrm-agent-frontend');
  fs.mkdirSync(path.join(frontend, 'node_modules', 'next'), { recursive: true });
  fs.writeFileSync(
    path.join(frontend, 'node_modules', 'next', 'package.json'),
    JSON.stringify({ name: 'next', engines: { node: floor } }),
  );
  return frontend;
}

/** An executable named `node` in a fresh directory; returns the file. */
function makeNodeFile(dir: string): string {
  fs.mkdirSync(dir, { recursive: true });
  const file = path.join(dir, NODE_FILE);
  fs.writeFileSync(file, '#!/bin/sh\n', { mode: 0o755 });
  return file;
}

/** Probe results by file; an unlisted file is not a runnable node. */
const probeFrom =
  (results: Record<string, NodeProbe>): ProbeNode =>
  (file) =>
    results[file] ?? null;
const real = (version: [number, number, number]): NodeProbe => ({ version, isBun: false });
const bunShim: NodeProbe = { version: [24, 3, 0], isBun: true };

beforeEach(() => {
  root = fs.mkdtempSync(path.join(os.tmpdir(), 'node-runtime-'));
});

afterEach(() => {
  fs.rmSync(root, { recursive: true, force: true });
});

describe('parseVersion', () => {
  it.each([
    ['v24.22.2', [24, 22, 2]],
    ['>=20.9.0', [20, 9, 0]],
    ['26.6.0\n', [26, 6, 0]],
  ])('reads %s', (text, expected) => {
    expect(parseVersion(text)).toEqual(expected);
  });

  it('refuses text without a full version', () => {
    expect(parseVersion('latest')).toBeNull();
    expect(parseVersion('20.9')).toBeNull();
  });
});

describe('resolveNodeRuntime', () => {
  it('takes the first real Node.js on PATH', () => {
    const frontend = makeFrontend();
    const first = makeNodeFile(path.join(root, 'a'));
    const second = makeNodeFile(path.join(root, 'b'));
    const probe = probeFrom({ [first]: real([22, 1, 0]), [second]: real([26, 6, 0]) });

    const found = resolveNodeRuntime({
      frontendRoot: frontend,
      envPath: [path.dirname(first), path.dirname(second)].join(path.delimiter),
      probe,
    });

    expect(found).toBe(first);
  });

  it("does not take Bun's node shim for a Node.js", () => {
    const frontend = makeFrontend();
    const shim = makeNodeFile(path.join(root, 'bun-node-123'));
    const homebrew = makeNodeFile(path.join(root, 'homebrew'));
    const probe = probeFrom({ [shim]: bunShim, [homebrew]: real([26, 6, 0]) });

    const found = resolveNodeRuntime({
      frontendRoot: frontend,
      envPath: [path.dirname(shim), path.dirname(homebrew)].join(path.delimiter),
      probe,
    });

    expect(found).toBe(homebrew);
  });

  it('skips a Node.js below the floor Next declares, and follows the floor when Next raises it', () => {
    const frontend = makeFrontend('>=20.9.0');
    const old = makeNodeFile(path.join(root, 'old'));
    const probe = probeFrom({ [old]: real([20, 8, 9]) });
    const options = { frontendRoot: frontend, envPath: path.dirname(old), probe };
    expect(resolveNodeRuntime(options)).toBeNull();

    const modern = probeFrom({ [old]: real([20, 9, 0]) });
    expect(resolveNodeRuntime({ ...options, probe: modern })).toBe(old);

    fs.writeFileSync(
      path.join(frontend, 'node_modules', 'next', 'package.json'),
      JSON.stringify({ engines: { node: '>=22.0.0' } }),
    );
    expect(resolveNodeRuntime({ ...options, probe: modern })).toBeNull();
  });

  it('falls back to the provisioned runtime when PATH has no usable Node.js', () => {
    const frontend = makeFrontend();
    const shim = makeNodeFile(path.join(root, 'bun-node-123'));
    const provisioned = makeNodeFile(provisionedNodeDir(frontend));
    const probe = probeFrom({ [shim]: bunShim, [provisioned]: real([24, 22, 2]) });

    expect(resolveNodeRuntime({ frontendRoot: frontend, envPath: path.dirname(shim), probe })).toBe(provisioned);
  });

  it('prefers a Node.js already on PATH over the provisioned one', () => {
    const frontend = makeFrontend();
    const onPath = makeNodeFile(path.join(root, 'homebrew'));
    const provisioned = makeNodeFile(provisionedNodeDir(frontend));
    const probe = probeFrom({ [onPath]: real([26, 6, 0]), [provisioned]: real([24, 22, 2]) });

    expect(resolveNodeRuntime({ frontendRoot: frontend, envPath: path.dirname(onPath), probe })).toBe(onPath);
  });

  it('ignores PATH entries that are missing, empty or not executable', () => {
    const frontend = makeFrontend();
    const notExecutable = path.join(root, 'plain', NODE_FILE);
    fs.mkdirSync(path.dirname(notExecutable), { recursive: true });
    fs.writeFileSync(notExecutable, 'x', { mode: 0o644 });
    const envPath = ['', path.join(root, 'missing'), path.dirname(notExecutable)].join(path.delimiter);
    const probe: ProbeNode = () => {
      throw new Error('a file that cannot run must never be probed');
    };

    if (process.platform !== 'win32') {
      expect(resolveNodeRuntime({ frontendRoot: frontend, envPath: envPath, probe })).toBeNull();
    }
  });

  it('reports a Next without a Node.js floor instead of guessing one', () => {
    const frontend = makeFrontend('latest');

    expect(() => resolveNodeRuntime({ frontendRoot: frontend, envPath: '' })).toThrow(NodeRuntimeError);
  });
});

describe('ensureNodeRuntime', () => {
  /** The desktop fetch script, replaced by one that writes `body` as `<output-dir>/<name>` (or fails). */
  function stubFetchScript(frontend: string, mode: 'installs' | 'fails'): string {
    const script = path.join(frontend, '..', 'myrm-agent-desktop', 'scripts', 'fetch_node_runtime.py');
    fs.mkdirSync(path.dirname(script), { recursive: true });
    const code =
      mode === 'fails'
        ? 'import sys\nsys.exit(1)\n'
        : [
            'import argparse, pathlib',
            'p = argparse.ArgumentParser()',
            "p.add_argument('--output-dir'); p.add_argument('--name')",
            'a = p.parse_args()',
            'out = pathlib.Path(a.output_dir); out.mkdir(parents=True, exist_ok=True)',
            "(out / a.name).write_text('#!/bin/sh\\n'); (out / a.name).chmod(0o755)",
            '',
          ].join('\n');
    fs.writeFileSync(script, code);
    return script;
  }

  it('returns an existing Node.js without fetching anything', () => {
    const frontend = makeFrontend();
    const onPath = makeNodeFile(path.join(root, 'homebrew'));

    expect(
      ensureNodeRuntime({
        frontendRoot: frontend,
        envPath: path.dirname(onPath),
        probe: probeFrom({ [onPath]: real([26, 6, 0]) }),
      }),
    ).toBe(onPath);
    expect(fs.existsSync(path.join(frontend, '..', 'myrm-agent-desktop'))).toBe(false);
  });

  it.skipIf(process.platform === 'win32')(
    'fetches the pinned runtime as `node` into the provisioned directory when none exists',
    () => {
      const frontend = makeFrontend();
      stubFetchScript(frontend, 'installs');
      const provisioned = path.join(provisionedNodeDir(frontend), NODE_FILE);
      const probe: ProbeNode = (file) => (file === provisioned ? real([24, 22, 2]) : null);

      expect(ensureNodeRuntime({ frontendRoot: frontend, envPath: '', probe })).toBe(provisioned);
    },
  );

  it.skipIf(process.platform === 'win32')('says how to fix it when the fetch fails', () => {
    const frontend = makeFrontend();
    stubFetchScript(frontend, 'fails');

    expect(() => ensureNodeRuntime({ frontendRoot: frontend, envPath: '', probe: probeFrom({}) })).toThrow(
      /Install Node\.js >= 20\.9\.0 from https:\/\/nodejs\.org/,
    );
  });

  it.skipIf(process.platform === 'win32')('rejects a fetched file that is not a usable Node.js', () => {
    const frontend = makeFrontend();
    stubFetchScript(frontend, 'installs');

    expect(() => ensureNodeRuntime({ frontendRoot: frontend, envPath: '', probe: probeFrom({}) })).toThrow(
      /not a usable Node\.js/,
    );
  });
});

describe('nodeEnv', () => {
  it("puts the chosen Node.js's directory first on PATH and keeps the rest", () => {
    const env = nodeEnv(path.join('/opt', 'node', 'bin', NODE_FILE), {
      PATH: ['/usr/bin', '/bin'].join(path.delimiter),
      KEEP: '1',
    });

    expect(env.PATH).toBe([path.join('/opt', 'node', 'bin'), '/usr/bin', '/bin'].join(path.delimiter));
    expect(env.KEEP).toBe('1');
  });
});

describe('probeNode', () => {
  it('tells the runtime that runs these tests apart from the other one', () => {
    const probe = probeNode(process.execPath);

    expect(probe).not.toBeNull();
    expect(probe?.isBun).toBe(Boolean(process.versions.bun));
  });

  it.skipIf(process.platform === 'win32')(
    'recognises a real bun binary, which is what Bun symlinks as its `node` shim',
    () => {
      const located = spawnSync('sh', ['-c', 'command -v bun'], { encoding: 'utf8' });
      const bun = located.stdout.trim();
      if (located.status !== 0 || !bun) {
        return; // no bun on this machine: nothing to recognise
      }
      // Bun's shim is a symlink to bun, so what the probe sees through it is the same binary.
      const shim = path.join(root, NODE_FILE);
      fs.symlinkSync(bun, shim);

      expect(probeNode(shim)?.isBun).toBe(true);
    },
  );

  it('returns null for a file that cannot run', () => {
    expect(probeNode(path.join(root, 'nope'))).toBeNull();
  });
});
