/**
 * A cloud backend for the sync layer tests: it serves the config rows the test lists (the core keys always exist,
 * empty unless listed), takes or refuses each write as the test decides, and records every write it receives.
 * Install it after mocking `@/lib/deploy-mode` to cloud mode.
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

export interface ServerRow {
  value: unknown;
  version: string;
  deviceId?: string;
}

export interface CloudBackendOptions {
  /** The rows the server holds. */
  rows?: Record<string, ServerRow>;
  /** How each write is received; read at request time. */
  answer?: (changes: ConfigChange[]) => WriteAnswer;
  /** Keys whose single read answers with this HTTP status; read at request time. */
  failingReads?: Record<string, number>;
}

const response = (status: number, body: unknown = {}) =>
  ({ ok: status >= 200 && status < 300, status, json: () => Promise.resolve(body) }) as Response;

const wireRecord = (key: string, row: ServerRow) => ({
  key,
  value: row.value,
  version: row.version,
  updatedAt: '2026-01-01T00:00:00.000Z',
  deviceId: row.deviceId ?? 'dev',
  encrypted: false,
});

export function serveCloudBackend(options: CloudBackendOptions = {}): RecordedWrite[] {
  const writes: RecordedWrite[] = [];
  const rowOf = (key: string): ServerRow | undefined =>
    options.rows?.[key] ?? (CORE_KEYS.includes(key) ? { value: {}, version: '1000_0' } : undefined);

  global.fetch = vi.fn((url: RequestInfo | URL, init?: RequestInit) => {
    const { pathname, searchParams } = new URL(String(url));
    if (init?.method === 'POST') {
      const { changes } = JSON.parse(String(init.body)) as { changes: ConfigChange[] };
      writes.push({ at: Date.now(), changes });
      const verdict = options.answer?.(changes) ?? 'accept';
      if (verdict !== 'accept') {
        return Promise.resolve(response(verdict, { detail: 'refused' }));
      }
      const newVersions = Object.fromEntries(changes.map((change) => [change.key, '2000_0']));
      return Promise.resolve(response(200, { success: true, conflicts: [], newVersions }));
    }
    if (pathname === '/config') {
      const keys = searchParams.get('keys')?.split(',') ?? [...CORE_KEYS, ...Object.keys(options.rows ?? {})];
      const rows = keys.flatMap((key) => {
        const row = rowOf(key);
        return row ? [[key, wireRecord(key, row)] as const] : [];
      });
      return Promise.resolve(response(200, { configs: Object.fromEntries(rows) }));
    }
    const key = pathname.split('/').at(-1) ?? '';
    const failure = options.failingReads?.[key];
    if (failure !== undefined) {
      return Promise.resolve(response(failure));
    }
    const row = rowOf(key);
    return Promise.resolve(row ? response(200, wireRecord(key, row)) : response(404));
  }) as unknown as typeof fetch;
  return writes;
}

/** The keys in the stored offline queue. */
export const storedKeys = (): string[] =>
  (JSON.parse(localStorage.getItem(OFFLINE_QUEUE_KEY) ?? '[]') as ConfigChange[]).map((change) => change.key);
