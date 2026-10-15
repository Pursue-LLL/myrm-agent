import { describe, it, expect } from 'vitest';
import {
  normalizeCronExpression,
  normalizeMcpConfig,
  generateAssetFingerprint,
  buildReconciliationReport,
  applyConflictResolution,
  formatSourceTypeLabel,
} from '../dataMigrationEngine';
import { FourDimensionalAssets } from '../dataMigrationTypes';

describe('dataMigrationEngine', () => {
  it('normalizes heterogeneous cron expressions to standard 5 fields', () => {
    // 6-field with seconds
    expect(normalizeCronExpression('0 30 9 * * 1-5')).toBe('30 9 * * 1-5');
    // standard 5-field
    expect(normalizeCronExpression('0 0 * * *')).toBe('0 0 * * *');
    // aliases
    expect(normalizeCronExpression('@daily')).toBe('0 0 * * *');
    expect(normalizeCronExpression('@hourly')).toBe('0 * * * *');
    expect(normalizeCronExpression('@weekly')).toBe('0 0 * * 0');
    expect(normalizeCronExpression('@monthly')).toBe('0 0 1 * *');
    // empty fallback
    expect(normalizeCronExpression('  ')).toBe('0 0 * * *');
  });

  it('normalizes heterogeneous MCP configurations with defaults', () => {
    const raw = {
      cmd: 'uvx',
      args: ['mcp-server-git'],
      env: { GIT_PATH: '/usr/bin/git' },
    };

    const normalized = normalizeMcpConfig('git-mcp', raw);
    expect(normalized.name).toBe('git-mcp');
    expect(normalized.transport).toBe('stdio');
    expect(normalized.command).toBe('uvx');
    expect(normalized.args).toEqual(['mcp-server-git']);
    expect(normalized.env?.GIT_PATH).toBe('/usr/bin/git');
    expect(normalized.enabled).toBe(true);

    // SSE fallback
    const rawSse = {
      type: 'sse',
      url: 'https://mcp.example.com/sse',
    };
    const normalizedSse = normalizeMcpConfig('sse-mcp', rawSse);
    expect(normalizedSse.transport).toBe('sse');
    expect(normalizedSse.url).toBe('https://mcp.example.com/sse');
  });

  it('generates asset fingerprints for deduplication across categories', () => {
    const fpTask = generateAssetFingerprint('task', {
      id: 't1',
      title: ' 构建报表 ',
      createdAt: 1000,
      status: 'completed',
    });
    expect(fpTask).toBe('task:构建报表');

    const fpCron = generateAssetFingerprint('cron', {
      id: 'c1',
      name: 'DB Backup',
      cronExpression: '0 0 * * *',
      taskTemplate: 'tpl',
      enabled: true,
    });
    expect(fpCron).toBe('cron:db backup:0 0 * * *');

    const fpMem = generateAssetFingerprint('memory', {
      id: 'm1',
      category: 'preference',
      content: '喜欢深色主题',
      confidence: 1,
      createdAt: 1000,
    });
    expect(fpMem).toBe('memory:preference:喜欢深色主题');

    const fpMcp = generateAssetFingerprint('mcp', {
      name: 'FetchServer',
      transport: 'stdio',
      enabled: true,
    });
    expect(fpMcp).toBe('mcp:fetchserver');
  });

  it('builds reconciliation report detecting new and duplicate assets', () => {
    const incoming: FourDimensionalAssets = {
      tasks: [
        { id: '1', title: 'Task New', createdAt: 1, status: 'completed' },
        { id: '2', title: 'Task Existing', createdAt: 2, status: 'completed' },
      ],
      cronJobs: [
        { id: 'c1', name: 'Cron New', cronExpression: '0 0 * * *', taskTemplate: '', enabled: true },
      ],
      memories: [],
      mcpConfigs: [],
    };

    const existingFingerprints = new Set<string>(['task:task existing']);

    const report = buildReconciliationReport(incoming, existingFingerprints, 'qoder_v1');
    expect(report.sourceType).toBe('qoder_v1');
    expect(report.tasks.total).toBe(2);
    expect(report.tasks.newCount).toBe(1);
    expect(report.tasks.duplicateCount).toBe(1);
    expect(report.cronJobs.total).toBe(1);
    expect(report.cronJobs.newCount).toBe(1);
    expect(report.cronJobs.duplicateCount).toBe(0);
  });

  it('applies conflict resolution with skip, overwrite, and rename strategies', () => {
    const incoming: FourDimensionalAssets = {
      tasks: [
        { id: '1', title: 'Task Duplicate', createdAt: 1, status: 'completed' },
      ],
      cronJobs: [],
      memories: [],
      mcpConfigs: [],
    };

    const existing = new Set<string>(['task:task duplicate']);

    // Skip strategy
    const skipped = applyConflictResolution(incoming, existing, 'skip');
    expect(skipped.tasks).toHaveLength(0);

    // Overwrite strategy
    const overwritten = applyConflictResolution(incoming, existing, 'overwrite');
    expect(overwritten.tasks).toHaveLength(1);
    expect(overwritten.tasks[0].title).toBe('Task Duplicate');

    // Rename strategy
    const renamed = applyConflictResolution(incoming, existing, 'rename');
    expect(renamed.tasks).toHaveLength(1);
    expect(renamed.tasks[0].title).toBe('Task Duplicate (迁移重名)');
  });

  it('formats human readable source type labels', () => {
    expect(formatSourceTypeLabel('qoder_v1')).toContain('Qoder');
    expect(formatSourceTypeLabel('hermes_legacy')).toContain('Hermes');
    expect(formatSourceTypeLabel('openclaw')).toContain('OpenClaw');
    expect(formatSourceTypeLabel('sqlite_backup')).toContain('SQLite');
    expect(formatSourceTypeLabel('custom_json')).toContain('JSON');
  });
});
