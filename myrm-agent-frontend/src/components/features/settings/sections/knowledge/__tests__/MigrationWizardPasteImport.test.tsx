/** @vitest-environment jsdom */
/**
 * [INPUT]
 * ../MigrationWizardSteps::ScanStep, PreviewStep (POS: 迁移向导扫描与预览步骤)
 * ../../../../../locales/en.json (POS: 英文文案 SSOT)
 *
 * [OUTPUT]
 * 粘贴导入通道与迁移告警文案回归测试。
 *
 * [POS]
 * 迁移向导粘贴通道与告警文案测试。断言粘贴文本可解析预览、导出提示词为真实文案、告警码走共享文案而不是裸码。
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const en = (await import('../../../../../../../locales/en.json')).default;

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'en'));

import type { MemoryImportDryRunResponse } from '@/services/memory/archive';
import { PreviewStep, ScanStep, type TranslationFn } from '../MigrationWizardSteps';

const wizardMessages = en.memory.migrationWizard as unknown as Record<string, unknown>;

const readCopy = (key: string): string | null => {
  const copy = key
    .split('.')
    .reduce<unknown>(
      (node, part) => (node && typeof node === 'object' ? (node as Record<string, unknown>)[part] : undefined),
      wizardMessages,
    );
  return typeof copy === 'string' ? copy : null;
};

const t: TranslationFn = (key, values) => {
  const copy = readCopy(key);
  if (copy === null) {
    return key;
  }
  return values ? copy.replace(/\{(\w+)\}/g, (_, name: string) => String(values[name] ?? `{${name}}`)) : copy;
};

const renderScan = (overrides: Partial<Parameters<typeof ScanStep>[0]> = {}) => {
  const props: Parameters<typeof ScanStep>[0] = {
    discovery: null,
    scanning: false,
    uploading: false,
    previewing: false,
    previewingSource: null,
    includeEpisodic: true,
    onIncludeEpisodicChange: vi.fn(),
    agents: [],
    targetAgentId: null,
    onTargetAgentIdChange: vi.fn(),
    onScan: vi.fn(),
    onUpload: vi.fn(),
    onPreview: vi.fn(),
    pasteText: '',
    pasting: false,
    onPasteTextChange: vi.fn(),
    onPastePreview: vi.fn(),
    t,
    ...overrides,
  };
  render(<ScanStep {...props} />);
  return props;
};

const dryRun: MemoryImportDryRunResponse = {
  dry_run_id: 'memory-import:test',
  payload_hash: 'hash',
  expires_at: '2026-01-02T01:00:00Z',
  result: {
    summary: {
      source: 'pasted_memory',
      version: '1',
      total_items: 2,
      mapped_items: 1,
      unmapped_items: 1,
      status: 'warning',
    },
    mappings: [],
    warnings: ['pasted_entries_over_limit', 'brand_new_warning_code'],
    normalized_data: { conversation: [{ content: 'We settled on Postgres 17' }] },
  },
  pending_skills: [],
  coverage_items: [],
  migration_lanes: [],
};

describe('migration wizard paste lane', () => {
  afterEach(cleanup);

  it('forwards pasted text and requests a preview', () => {
    const props = renderScan({ pasteText: '## FACTS\n- Uses Postgres' });

    fireEvent.change(screen.getByTestId('migration-paste-textarea'), { target: { value: '## RULES\n- Answer short' } });
    expect(props.onPasteTextChange).toHaveBeenCalledWith('## RULES\n- Answer short');

    const previewButton = screen.getByRole('button', { name: /Parse and preview/ });
    expect(previewButton).toBeEnabled();
    fireEvent.click(previewButton);
    expect(props.onPastePreview).toHaveBeenCalledTimes(1);
  });

  it('keeps the preview action disabled while nothing is pasted', () => {
    renderScan();

    expect(screen.getByRole('button', { name: /Parse and preview/ })).toBeDisabled();
  });

  it('copies the real export prompt for assistants without an export package', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    renderScan();

    fireEvent.click(screen.getByRole('button', { name: /Copy export prompt/ }));

    expect(writeText).toHaveBeenCalledTimes(1);
    expect(writeText.mock.calls[0][0]).toContain('## RULES');
    expect(writeText.mock.calls[0][0]).toContain('## PREFERENCES');
  });
});

describe('migration wizard preview copy', () => {
  beforeEach(() => {
    Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true });
  });

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
        }}
        dryRun={dryRun}
        importing={false}
        importSecrets={false}
        onImportSecretsChange={vi.fn()}
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
  });
});
