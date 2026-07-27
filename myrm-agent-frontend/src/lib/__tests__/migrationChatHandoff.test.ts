/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  clearMigrationReadinessAnchor,
  consumeMigrationReadinessAnchor,
  consumeMigrationReadinessAnchorForAgent,
  queueMigrationReadinessAnchor,
  readMigrationReadinessAnchor,
} from '../migrationChatHandoff';

const ANCHOR_KEY = 'myrm:migration-readiness-anchor';

describe('migrationChatHandoff readiness anchor', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    vi.useRealTimers();
  });

  it('queues and reads anchor without consuming', () => {
    queueMigrationReadinessAnchor({
      importBatchId: 'memory-import-batch:test',
      readinessStatus: 'warning',
      targetAgentId: 'agent-123',
    });

    expect(readMigrationReadinessAnchor()).toEqual({
      importBatchId: 'memory-import-batch:test',
      readinessStatus: 'warning',
      targetAgentId: 'agent-123',
      queuedAt: expect.any(String),
    });
    expect(localStorage.getItem(ANCHOR_KEY)).toBeTruthy();
  });

  it('consumes anchor only for matching agent', () => {
    queueMigrationReadinessAnchor({
      importBatchId: 'memory-import-batch:test',
      readinessStatus: 'ready',
      targetAgentId: 'agent-123',
    });

    expect(consumeMigrationReadinessAnchorForAgent('agent-other')).toBeNull();
    expect(readMigrationReadinessAnchor()).not.toBeNull();

    expect(consumeMigrationReadinessAnchorForAgent('agent-123')).toEqual({
      importBatchId: 'memory-import-batch:test',
      readinessStatus: 'ready',
      targetAgentId: 'agent-123',
      queuedAt: expect.any(String),
    });
    expect(readMigrationReadinessAnchor()).toBeNull();
  });

  it('expires stale anchors', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-01-01T00:00:00.000Z'));
    queueMigrationReadinessAnchor({
      importBatchId: 'memory-import-batch:test',
      readinessStatus: 'ready',
      targetAgentId: 'agent-123',
    });

    vi.setSystemTime(new Date('2026-01-01T01:00:00.000Z'));
    expect(readMigrationReadinessAnchor()).toBeNull();
    expect(localStorage.getItem(ANCHOR_KEY)).toBeNull();
  });

  it('consumes and clears anchor via legacy consume helper', () => {
    queueMigrationReadinessAnchor({
      importBatchId: 'memory-import-batch:test',
      readinessStatus: 'ready',
      targetAgentId: 'agent-123',
    });

    expect(consumeMigrationReadinessAnchor()).toEqual({
      importBatchId: 'memory-import-batch:test',
      readinessStatus: 'ready',
      targetAgentId: 'agent-123',
      queuedAt: expect.any(String),
    });
    expect(readMigrationReadinessAnchor()).toBeNull();
  });

  it('migrates legacy sessionStorage anchor into localStorage', () => {
    sessionStorage.setItem(
      ANCHOR_KEY,
      JSON.stringify({
        importBatchId: 'memory-import-batch:legacy',
        readinessStatus: 'warning',
        targetAgentId: 'agent-legacy',
        queuedAt: new Date().toISOString(),
      }),
    );

    expect(readMigrationReadinessAnchor()).toEqual({
      importBatchId: 'memory-import-batch:legacy',
      readinessStatus: 'warning',
      targetAgentId: 'agent-legacy',
      queuedAt: expect.any(String),
    });
    expect(localStorage.getItem(ANCHOR_KEY)).toBeTruthy();
    expect(sessionStorage.getItem(ANCHOR_KEY)).toBeNull();
  });

  it('returns null for malformed payload', () => {
    localStorage.setItem(ANCHOR_KEY, '{"importBatchId": 1, "readinessStatus": "ready"}');
    expect(readMigrationReadinessAnchor()).toBeNull();
    clearMigrationReadinessAnchor();
    expect(localStorage.getItem(ANCHOR_KEY)).toBeNull();
  });
});
