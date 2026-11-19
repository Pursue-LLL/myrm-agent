/** @vitest-environment jsdom */
/**
 * [INPUT]
 * ../PreviewStep (POS: 迁移向导预览步骤)
 *
 * [OUTPUT]
 * 预览页可信来源声明门禁的回归测试。
 *
 * [POS]
 * 来源是 Pi、或带有技能（来源技能数或待提交技能）时，用户先勾选「可信来源」声明才能确认导入；
 * 其余来源不出现该声明，可直接确认导入。
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { MemoryImportDryRunResponse } from '@/services/memory/archive';
import { PreviewStep } from '../PreviewStep';
import type { TranslationFn } from '../wizardShared';

const t: TranslationFn = (key, values) => (values ? `${key}:${JSON.stringify(values)}` : key);

describe('PreviewStep trusted source disclosure gate', () => {
  const dummyDryRun: MemoryImportDryRunResponse = {
    dry_run_id: 'dry-run-123',
    payload_hash: 'hash-123',
    expires_at: '2026-01-01T00:00:00Z',
    result: {
      summary: {
        version: '1',
        total_items: 5,
        mapped_items: 5,
        unmapped_items: 0,
        status: 'ready' as const,
        source: 'pi',
      },
      mappings: [],
      warnings: [],
      normalized_data: {},
    },
    coverage_items: [],
    migration_lanes: [],
    pending_skills_total: 2,
    pending_skills: [
      {
        name: 'test-skill',
        content: 'echo hi',
      },
    ],
  };

  it('requires trusted source checkbox when importing from pi competitor', () => {
    const onConfirm = vi.fn();
    render(
      <PreviewStep
        source={{
          competitor: 'pi',
          root: '/home/user/.pi',
          confidence: 'high',
          files: [],
          memory_count_estimate: 5,
          skill_count: 2,
          has_api_keys: false,
          can_import_secrets: false,
        }}
        dryRun={dummyDryRun}
        importing={false}
        importSecrets={false}
        onImportSecretsChange={vi.fn()}
        importSessions
        onImportSessionsChange={vi.fn()}
        onConfirm={onConfirm}
        onBack={vi.fn()}
        t={t}
      />,
    );

    const checkbox = screen.getByTestId('migration-trusted-source-checkbox');
    expect(checkbox).not.toBeChecked();

    const confirmBtn = screen.getByRole('button', { name: 'preview.confirmImport' });
    expect(confirmBtn).toBeDisabled();

    fireEvent.click(checkbox);
    expect(checkbox).toBeChecked();
    expect(confirmBtn).not.toBeDisabled();

    fireEvent.click(confirmBtn);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('does not render trusted source disclosure when source is not pi and has no skills', () => {
    const onConfirm = vi.fn();
    render(
      <PreviewStep
        source={{
          competitor: 'hermes',
          root: '/home/user/.hermes',
          confidence: 'medium',
          files: [],
          memory_count_estimate: 3,
          skill_count: 0,
          has_api_keys: false,
          can_import_secrets: false,
        }}
        dryRun={{
          ...dummyDryRun,
          pending_skills: [],
          result: {
            ...dummyDryRun.result,
            summary: {
              ...dummyDryRun.result.summary,
              source: 'hermes',
            },
          },
        }}
        importing={false}
        importSecrets={false}
        onImportSecretsChange={vi.fn()}
        importSessions
        onImportSessionsChange={vi.fn()}
        onConfirm={onConfirm}
        onBack={vi.fn()}
        t={t}
      />,
    );

    expect(screen.queryByTestId('migration-trusted-source-checkbox')).toBeNull();
    const confirmBtn = screen.getByRole('button', { name: 'preview.confirmImport' });
    expect(confirmBtn).not.toBeDisabled();
  });
});
