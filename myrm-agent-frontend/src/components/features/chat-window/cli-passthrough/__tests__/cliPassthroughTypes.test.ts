import { describe, it, expect } from 'vitest';
import type {
  CliPassThroughMode,
  CliExecutionStatus,
  CliCommandRecord,
  CliGuardAuditResult,
  CliPassthroughStoreState,
} from '../cliPassthroughTypes';

describe('cliPassthroughTypes', () => {
  it('validates CLI pass-through types and contract structure', () => {
    const visibleMode: CliPassThroughMode = 'visible_to_context';
    const inspectionMode: CliPassThroughMode = 'user_inspection_only';
    expect(visibleMode).toBe('visible_to_context');
    expect(inspectionMode).toBe('user_inspection_only');

    const status: CliExecutionStatus = 'success';
    expect(status).toBe('success');

    const record: CliCommandRecord = {
      id: 'cmd-1',
      rawInput: '! npm test',
      command: 'npm test',
      mode: 'visible_to_context',
      status: 'success',
      output: 'All 15 tests passed',
      exitCode: 0,
      durationMs: 420,
      timestamp: 1760000000000,
    };
    expect(record.command).toBe('npm test');
    expect(record.exitCode).toBe(0);
    expect(record.durationMs).toBe(420);

    const auditPass: CliGuardAuditResult = {
      allowed: true,
    };
    expect(auditPass.allowed).toBe(true);

    const auditBlock: CliGuardAuditResult = {
      allowed: false,
      reason: '高危操作',
    };
    expect(auditBlock.allowed).toBe(false);
    expect(auditBlock.reason).toBe('高危操作');

    const storeState: CliPassthroughStoreState = {
      history: [record],
      activeCommand: record,
      isDrawerOpen: true,
      isExecuting: false,
    };
    expect(storeState.history.length).toBe(1);
    expect(storeState.isDrawerOpen).toBe(true);
  });
});
