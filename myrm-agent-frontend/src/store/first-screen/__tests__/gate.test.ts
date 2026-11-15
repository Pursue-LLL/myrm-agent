import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const runtime = vi.hoisted(() => ({
  tauri: false,
  local: true,
  remote: false,
}));

vi.mock('@/lib/deploy-mode', () => ({
  isTauriRuntime: () => runtime.tauri,
  isLocalMode: () => runtime.local,
  isRemoteGatewayActive: () => runtime.remote,
}));

import { isFirstScreenSnapshotEnabled } from '../gate';

beforeEach(() => {
  runtime.tauri = false;
  runtime.local = true;
  runtime.remote = false;
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe('isFirstScreenSnapshotEnabled', () => {
  it('is on in the desktop window and off in a browser by default', () => {
    runtime.tauri = true;
    expect(isFirstScreenSnapshotEnabled()).toBe(true);

    runtime.tauri = false;
    expect(isFirstScreenSnapshotEnabled()).toBe(false);
  });

  it('is off when the desktop window talks to a remote server', () => {
    runtime.tauri = true;
    runtime.remote = true;

    expect(isFirstScreenSnapshotEnabled()).toBe(false);
  });

  it('is off everywhere when the flag says so', () => {
    runtime.tauri = true;
    vi.stubEnv('NEXT_PUBLIC_FIRST_SCREEN_SNAPSHOT', 'off');

    expect(isFirstScreenSnapshotEnabled()).toBe(false);
  });

  it('extends to any local-mode origin when the flag says local, but never to a hosted build', () => {
    vi.stubEnv('NEXT_PUBLIC_FIRST_SCREEN_SNAPSHOT', 'local');
    expect(isFirstScreenSnapshotEnabled()).toBe(true);

    runtime.local = false;
    expect(isFirstScreenSnapshotEnabled()).toBe(false);
  });

  it('reads the flag case-insensitively and falls back to the desktop default for anything else', () => {
    runtime.tauri = true;
    vi.stubEnv('NEXT_PUBLIC_FIRST_SCREEN_SNAPSHOT', ' OFF ');
    expect(isFirstScreenSnapshotEnabled()).toBe(false);

    vi.stubEnv('NEXT_PUBLIC_FIRST_SCREEN_SNAPSHOT', 'maybe');
    expect(isFirstScreenSnapshotEnabled()).toBe(true);
  });

  it('is off while rendering on the server', () => {
    runtime.tauri = true;
    vi.stubGlobal('window', undefined);

    expect(isFirstScreenSnapshotEnabled()).toBe(false);
  });
});
