/** @vitest-environment jsdom */
/**
 * [INPUT]
 * ../PreviewStep (POS: 迁移向导预览步骤)
 * ../../../../../../../../locales/en.json (POS: 英文文案 SSOT)
 *
 * [OUTPUT]
 * 预览分组名与车道标题的文案回归测试。
 *
 * [POS]
 * 码表内的分组 / 车道显示译文；服务端新增的、码表之外的取值原样显示，不露出键路径。
 */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import en from '../../../../../../../../locales/en.json';
import type { MemoryImportDryRunResponse } from '@/services/memory/archive';
import { LANE_LABEL_CODES } from '../PreviewCards';
import { PREVIEW_BUCKET_CODES } from '../PreviewPanels';
import { PreviewStep } from '../PreviewStep';
import type { TranslationFn } from '../wizardShared';

const wizardMessages = en.memory.migrationWizard as unknown as Record<string, unknown>;

/** 缺键时返回键路径，与 next-intl 一致：测试因此分得出「显示了原值」和「露出了键路径」。 */
const t: TranslationFn = (key) => {
  const copy = key
    .split('.')
    .reduce<unknown>(
      (node, part) => (node && typeof node === 'object' ? (node as Record<string, unknown>)[part] : undefined),
      wizardMessages,
    );
  return typeof copy === 'string' ? copy : key;
};

const dryRun: MemoryImportDryRunResponse = {
  dry_run_id: 'memory-import:test',
  payload_hash: 'hash',
  expires_at: '2026-01-02T01:00:00Z',
  result: {
    summary: {
      source: 'hermes',
      version: '1',
      total_items: 2,
      mapped_items: 2,
      unmapped_items: 0,
      status: 'ready',
    },
    mappings: [],
    warnings: [],
    normalized_data: {
      conversation: [{ content: 'We settled on Postgres 17' }],
      brand_new_bucket: [{ content: 'Something the importer added later' }],
    },
  },
  pending_skills: [],
  pending_skills_total: 0,
  coverage_items: [],
  migration_lanes: [
    { lane: 'skill', status: 'review', label: 'skill_lane', detail: '1 skill(s) pending review' },
    { lane: 'extra', status: 'ready', label: 'brand_new_lane', detail: 'extra lane' },
  ],
};

describe('migration wizard preview group labels', () => {
  afterEach(cleanup);

  it('has copy for every preview bucket and lane title the wizard localizes', () => {
    const preview = en.memory.migrationWizard.preview as unknown as {
      previewBucket: Record<string, string>;
      laneLabels: Record<string, string>;
    };

    expect(PREVIEW_BUCKET_CODES.filter((bucket) => !(bucket in preview.previewBucket))).toEqual([]);
    expect(LANE_LABEL_CODES.filter((label) => !(label in preview.laneLabels))).toEqual([]);
  });

  it('translates known groups and shows unknown ones as the server sent them', () => {
    render(
      <PreviewStep
        source={{
          competitor: 'hermes',
          root: '/home/user/.hermes',
          confidence: 'high',
          files: [],
          memory_count_estimate: 2,
          skill_count: 1,
          has_api_keys: false,
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

    expect(screen.getByText('Dialogue')).toBeInTheDocument();
    expect(screen.getByText('brand_new_bucket')).toBeInTheDocument();
    expect(screen.queryByText('preview.previewBucket.brand_new_bucket')).toBeNull();
    expect(screen.getByText('Skills')).toBeInTheDocument();
    expect(screen.getByText('brand_new_lane')).toBeInTheDocument();
    expect(screen.queryByText('preview.laneLabels.brand_new_lane')).toBeNull();
  });
});
