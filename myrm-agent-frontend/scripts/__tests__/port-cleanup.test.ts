// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { foreignListenersOnPort, killListenersOnPort, listPidsOnPort } from '../port-cleanup';
import { exitsWithin, freePort, isAlive, startProcess, stopAllProcesses } from './helpers/process-fixtures';

const LISTENER = `
  const server = require('net').createServer();
  server.listen(Number(process.argv[1]), '127.0.0.1', () => console.log('ready'));
`;
const NEXT_DEV_ARGV = ['/repo/myrm-agent-frontend/node_modules/next/dist/bin/next', 'dev', '-p'];
const DESKTOP_UI_ARGV = ['/Applications/Myrm.app/myrm-agent-frontend/.next/standalone/server.js'];

const listenOn = (port: number, namespace: string | null, argv: string[] = []) =>
  startProcess(LISTENER, [String(port), ...argv], namespace);

describe('killListenersOnPort', () => {
  beforeEach(() => {
    vi.stubEnv('MYRM_RUNTIME_NAMESPACE', 'shared');
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    stopAllProcesses();
  });

  it('leaves a listener stamped by another runtime running — the user stack on the default port', async () => {
    const port = await freePort();
    const userStack = await listenOn(port, 'user');
    expect(killListenersOnPort(port, true)).toBe(0);
    expect(await exitsWithin(userStack, 1500)).toBe(false);
    expect(foreignListenersOnPort(port)).toEqual([String(userStack.pid)]);
  });

  it('reclaims a listener this runtime started', async () => {
    const port = await freePort();
    const own = await listenOn(port, 'shared');
    expect(killListenersOnPort(port, true)).toBe(1);
    expect(await exitsWithin(own, 5000)).toBe(true);
    expect(foreignListenersOnPort(port)).toEqual([]);
  });

  it('reclaims the un-stamped next dev an earlier bare `bun run dev` left behind', async () => {
    const port = await freePort();
    const leftover = await listenOn(port, null, [...NEXT_DEV_ARGV, String(port)]);
    expect(killListenersOnPort(port, true)).toBe(1);
    expect(await exitsWithin(leftover, 5000)).toBe(true);
  });

  it.each([
    ['an un-stamped program unrelated to this frontend', []],
    ['an un-stamped production server of this frontend (the desktop client)', DESKTOP_UI_ARGV],
  ])('leaves %s running', async (_label, argv) => {
    const port = await freePort();
    const bystander = await listenOn(port, null, argv);
    expect(killListenersOnPort(port, true)).toBe(0);
    expect(await exitsWithin(bystander, 1500)).toBe(false);
    expect(foreignListenersOnPort(port)).toEqual([String(bystander.pid)]);
  });

  it('does not take an un-stamped listener for a leftover next dev because a shell above it mentions one', async () => {
    const port = await freePort();
    const shellNote = '/repo/myrm-agent-frontend/node_modules/next/dist/bin/next dev';
    await startProcess(LISTENER, [String(port)], null, { shellNote });
    const [listener] = listPidsOnPort(port).map(Number);
    expect(killListenersOnPort(port, true)).toBe(0);
    await new Promise((resolve) => setTimeout(resolve, 1500));
    expect(isAlive(listener)).toBe(true);
  });
});
