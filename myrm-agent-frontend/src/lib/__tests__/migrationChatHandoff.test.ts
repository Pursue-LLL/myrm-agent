/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it } from 'vitest';

import {
  clearMigrationReadinessAnchor,
  consumeMigrationReadinessAnchor,
  queueMigrationReadinessAnchor,
  readMigrationReadinessAnchor,
} from '../migrationChatHandoff';

const ANCHOR_KEY = 'myrm:migration-readiness-anchor';

describe('migrationChatHandoff readiness anchor', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('queues and reads anchor without consuming', () => {
    queueMigrationReadinessAnchor({
      importBatchId: 'memory-import-batch:test',
      readinessStatus: 'warning',
    });

    expect(readMigrationReadinessAnchor()).toEqual({
      importBatchId: 'memory-import-batch:test',
      readinessStatus: 'warning',
    });
    expect(sessionStorage.getItem(ANCHOR_KEY)).toBeTruthy();
  });

  it('consumes and clears anchor', () => {
    queueMigrationReadinessAnchor({
      importBatchId: 'memory-import-batch:test',
      readinessStatus: 'ready',
    });

    expect(consumeMigrationReadinessAnchor()).toEqual({
      importBatchId: 'memory-import-batch:test',
      readinessStatus: 'ready',
    });
    expect(readMigrationReadinessAnchor()).toBeNull();
  });

  it('returns null for malformed payload', () => {
    sessionStorage.setItem(ANCHOR_KEY, '{"importBatchId": 1, "readinessStatus": "ready"}');
    expect(readMigrationReadinessAnchor()).toBeNull();
    clearMigrationReadinessAnchor();
    expect(sessionStorage.getItem(ANCHOR_KEY)).toBeNull();
  });
});
