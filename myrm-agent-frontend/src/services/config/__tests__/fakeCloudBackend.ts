/**
 * A cloud backend for the outbox tests: it serves the core config keys, takes or refuses each write as the test
 * decides, and records every write it receives. Install it after mocking `@/lib/deploy-mode` to cloud mode.
 */

import { vi } from 'vitest';
import type { ConfigChange } from '@/services/config/types';

export const CORE_KEYS = ['providers', 'chatSettings', 'personalSettings'];
export const OFFLINE_QUEUE_KEY = 'config-offline-queue';

/** `'accept'` stores the write; a number answers the whole write with that HTTP status (503: backend not available). */
export type WriteAnswer = 'accept' | number;

export interface RecordedWrite {
  at: number;
  changes: ConfigChange[];
}

const response = (status: number, body: unknown = {}) =>
  ({ ok: status >= 200 && status < 300, status, json: () => Promise.resolve(body) }) as Response;

const wireRecord = (key: string) => ({
  key,
  value: {},
  version: '1000_0',
  updatedAt: '2026-01-01T00:00:00.000Z',
  deviceId: 'dev',
  encrypted: false,
});

export function serveCloudBackend(answer: (changes: ConfigChange[]) => WriteAnswer = () => 'accept'): RecordedWrite[] {
  const writes: RecordedWrite[] = [];
  global.fetch = vi.fn((_url: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method !== 'POST') {
      return Promise.resolve(
        response(200, { configs: Object.fromEntries(CORE_KEYS.map((key) => [key, wireRecord(key)])) }),
      );
    }
    const { changes } = JSON.parse(String(init.body)) as { changes: ConfigChange[] };
    writes.push({ at: Date.now(), changes });
    const verdict = answer(changes);
    if (verdict !== 'accept') {
      return Promise.resolve(response(verdict, { detail: 'refused' }));
    }
    const newVersions = Object.fromEntries(changes.map((change) => [change.key, '2000_0']));
    return Promise.resolve(response(200, { success: true, conflicts: [], newVersions }));
  }) as unknown as typeof fetch;
  return writes;
}

/** The keys in the stored offline queue. */
export const storedKeys = (): string[] =>
  (JSON.parse(localStorage.getItem(OFFLINE_QUEUE_KEY) ?? '[]') as ConfigChange[]).map((change) => change.key);
