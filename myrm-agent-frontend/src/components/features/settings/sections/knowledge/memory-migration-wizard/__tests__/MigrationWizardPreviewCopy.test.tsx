/** @vitest-environment jsdom */
/**
 * [INPUT]
 * ../PreviewStep (POS: 迁移向导预览步骤)
 * ../PreviewPanels (POS: 预览参考面板，导出映射状态码表 MAPPING_STATUS_CODES)
 * ../wizardShared (POS: 覆盖标签键表 COVERAGE_LABEL_KEYS)
 * ./wizardTestKit (POS: 迁移向导测试共用夹具)
 * ../../../../../../../../locales/en.json (POS: 英文文案 SSOT)
 *
 * [OUTPUT]
 * 预览页文案回归测试。
 *
 * [POS]
 * 预览页的文案契约。告警码走共享文案、未知码回退为可读文字；映射状态与覆盖项在语言包里都有译文；
 * 评审编号不外露、到期时间按界面语言格式化；来源技能超过评审上限时说明被略去的数量。
 */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import en from '../../../../../../../../locales/en.json';
import type { MemoryImportDryRunResponse } from '@/services/memory/archive';
import { MAPPING_STATUS_CODES } from '../PreviewPanels';
import { PreviewStep } from '../PreviewStep';
import { COVERAGE_LABEL_KEYS } from '../wizardShared';
import { dryRun, t } from './wizardTestKit';

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'en'));

describe('migration wizard preview copy', () => {
  afterEach(cleanup);

  it('renders shared warning copy and humanizes unknown codes', () => {
    render(
      <PreviewStep
        source={{
          competitor: 'pasted',
          root: '',
          confidence: 'high',
          files: [],
          memory_count_estimate: 2,
          skill_count: 0,
          has_api_keys: false,
          can_import_secrets: false,
        }}
        dryRun={dryRun}
        importing={false}
        importSecrets={false}
        onImportSecretsChange={vi.fn()}
        importSessions
        onImportSessionsChange={vi.fn()}
        onConfirm={vi.fn()}
        onBack={vi.fn()}
        t={t}
      />,
    );

    expect(
      screen.getByText('One paste contained too many entries; split the export into several pastes.'),
    ).toBeInTheDocument();
    expect(screen.getByText('Brand new warning code')).toBeInTheDocument();
    expect(screen.queryByText('pasted_entries_over_limit')).toBeNull();
    expect(screen.getByText('Dialogue')).toBeInTheDocument();
    expect(screen.getByText('We settled on Postgres 17')).toBeInTheDocument();
    expect(
      screen.getByText('Entries whose content already exists in memory are merged or skipped during import.'),
    ).toBeInTheDocument();
  });

  it('localizes mapping statuses instead of exposing adapter codes', () => {
    const withMappings: MemoryImportDryRunResponse = {
      ...dryRun,
      result: {
        ...dryRun.result,
        mappings: [
          {
            source_bucket: 'MEMORY.md',
            target_bucket: 'semantic',
            status: 'mapped',
            item_count: 2,
            imported_count: 2,
            unmapped_count: 0,
            reason: '',
          },
          {
            source_bucket: 'SOUL.md',
            target_bucket: 'profile',
            status: 'partially_mapped',
            item_count: 2,
            imported_count: 1,
            unmapped_count: 1,
            reason: '',
          },
          {
            source_bucket: 'skills',
            target_bucket: null,
            status: 'unsupported',
            item_count: 1,
            imported_count: 0,
            unmapped_count: 1,
            reason: '',
          },
          {
            source_bucket: 'cron',
            target_bucket: null,
            status: 'dropped',
            item_count: 1,
            imported_count: 0,
            unmapped_count: 1,
            reason: '',
          },
        ],
      },
    };

    render(
      <PreviewStep
        source={{
          competitor: 'pasted',
          root: '',
          confidence: 'high',
          files: [],
          memory_count_estimate: 2,
          skill_count: 0,
          has_api_keys: false,
          can_import_secrets: false,
        }}
        dryRun={withMappings}
        importing={false}
        importSecrets={false}
        onImportSecretsChange={vi.fn()}
        importSessions
        onImportSessionsChange={vi.fn()}
        onConfirm={vi.fn()}
        onBack={vi.fn()}
        t={t}
      />,
    );

    expect(screen.getByText('Mapped')).toBeInTheDocument();
    expect(screen.getByText('Partially mapped')).toBeInTheDocument();
    expect(screen.getByText('Not imported')).toBeInTheDocument();
    expect(screen.getByText('Skipped')).toBeInTheDocument();
    expect(screen.queryByText('partially_mapped')).toBeNull();
  });

  it('has copy for every mapping status the adapter can emit', () => {
    const mappingStatus = en.memory.migrationWizard.preview.mappingStatus as unknown as Record<string, string>;
    const missing = MAPPING_STATUS_CODES.filter((status) => !(status in mappingStatus));

    expect(missing).toEqual([]);
  });

  it('has copy for every coverage label the wizard localizes', () => {
    const coverageLabels = en.memory.migrationWizard.preview.coverageLabels as unknown as Record<string, string>;
    const missing = COVERAGE_LABEL_KEYS.filter((label) => !(label in coverageLabels));

    expect(missing).toEqual([]);
  });

  it('does not expose the review id and formats the expiry with the app locale', () => {
    render(
      <PreviewStep
        source={{
          competitor: 'pasted',
          root: '',
          confidence: 'high',
          files: [],
          memory_count_estimate: 2,
          skill_count: 0,
          has_api_keys: false,
          can_import_secrets: false,
        }}
        dryRun={dryRun}
        importing={false}
        importSecrets={false}
        onImportSecretsChange={vi.fn()}
        importSessions
        onImportSessionsChange={vi.fn()}
        onConfirm={vi.fn()}
        onBack={vi.fn()}
        t={t}
      />,
    );

    expect(screen.queryByText(/memory-import:test/)).toBeNull();
    expect(screen.getByText(/Expires at/)).toBeInTheDocument();
    expect(screen.queryByText(/2026-01-02T01:00:00Z/)).toBeNull();
  });

  it('says how many skills the import leaves out when the source exceeds the review cap', () => {
    render(
      <PreviewStep
        source={{
          competitor: 'claude',
          root: '/home/user/.claude',
          confidence: 'high',
          files: [],
          memory_count_estimate: 4,
          skill_count: 3,
          has_api_keys: false,
          can_import_secrets: false,
        }}
        dryRun={{
          ...dryRun,
          pending_skills: [{ name: 'review', content: 'Review code' }],
          pending_skills_total: 3,
        }}
        importing={false}
        importSecrets={false}
        onImportSecretsChange={vi.fn()}
        importSessions
        onImportSessionsChange={vi.fn()}
        onConfirm={vi.fn()}
        onBack={vi.fn()}
        t={t}
      />,
    );

    expect(screen.getByText('Only the first 1 of 3 skills are imported; the rest are left out.')).toBeInTheDocument();
  });
});
