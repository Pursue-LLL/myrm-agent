/** @vitest-environment jsdom */
/**
 * [INPUT]
 * ../memory-migration-wizard/ScanStep (POS: 迁移向导扫描步骤)
 * ../memory-migration-wizard/PreviewStep (POS: 迁移向导预览步骤)
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

const en = (await import('../../../../../../../../locales/en.json')).default;

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'en'));

import { useTranslations } from 'next-intl';

import type { MemoryImportDryRunResponse } from '@/services/memory/archive';
import { LANE_DETAIL_CODES } from '../PreviewCards';
import { MAPPING_STATUS_CODES } from '../PreviewPanels';
import { PreviewStep } from '../PreviewStep';
import { ScanStep } from '../ScanStep';
import { COVERAGE_LABEL_KEYS, type TranslationFn } from '../wizardShared';

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
    pasteModelExtraction: false,
    onPasteTextChange: vi.fn(),
    onPasteModelExtractionChange: vi.fn(),
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
  pending_skills_total: 0,
  coverage_items: [],
  migration_lanes: [],
};

function RealIntlPreviewStep(props: Omit<Parameters<typeof PreviewStep>[0], 't'>) {
  const t = useTranslations('memory.migrationWizard');
  return <PreviewStep {...props} t={t} />;
}

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

  it('keeps model-assisted extraction opt-in and reports the choice', () => {
    const props = renderScan();
    const toggle = screen.getByTestId('migration-paste-model-toggle');

    expect(toggle).not.toBeChecked();
    expect(
      screen.getByText(
        'The text goes to the model configured for this agent; the result still needs your review before anything is saved.',
      ),
    ).toBeInTheDocument();

    fireEvent.click(toggle);
    expect(props.onPasteModelExtractionChange).toHaveBeenCalledWith(true);
  });

  it('states the paste size budget next to the textarea', () => {
    renderScan();

    expect(
      screen.getByText('Up to 4 MB per paste. Longer exports can be split into several pastes.'),
    ).toBeInTheDocument();
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

  it('has copy for every lane fragment code the wizard knows', () => {
    const laneDetailCopy = en.memory.migrationWizard.preview.laneDetail as unknown as Record<string, string>;
    const missing = LANE_DETAIL_CODES.filter((code) => !(code in laneDetailCopy));

    expect(missing).toEqual([]);
  });

  it('renders lane details from localized parts instead of the raw detail line', () => {
    const withLanes: MemoryImportDryRunResponse = {
      ...dryRun,
      migration_lanes: [
        {
          lane: 'instruction',
          status: 'ready',
          label: 'instruction_lane',
          detail: 'agent persona (120 chars), 9000 chars total (large)',
          detail_parts: [
            { code: 'instruction_persona', params: { chars: 120 } },
            { code: 'instruction_large', params: { chars: 9000 } },
          ],
        },
      ],
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
        }}
        dryRun={withLanes}
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

    expect(screen.getByText('120 chars of persona · 9000 chars total, above the recommended size')).toBeInTheDocument();
    expect(screen.queryByText('agent persona (120 chars), 9000 chars total (large)')).toBeNull();
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

  it('localizes the credential pool coverage row', () => {
    const withCredentialPool: MemoryImportDryRunResponse = {
      ...dryRun,
      coverage_items: [{ key: 'credential_pool', status: 'ready', label: 'credential_pool_migration' }],
    };

    render(
      <PreviewStep
        source={{
          competitor: 'hermes',
          root: '/home/user/.hermes',
          confidence: 'high',
          files: [],
          memory_count_estimate: 2,
          skill_count: 0,
          has_api_keys: true,
        }}
        dryRun={withCredentialPool}
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

    expect(screen.getByText('Credential pool migration')).toBeInTheDocument();
    expect(screen.queryByText('credential_pool_migration')).toBeNull();
  });

  it('renders plural lane fragments through the real translator', () => {
    const withPluralLanes: MemoryImportDryRunResponse = {
      ...dryRun,
      migration_lanes: [
        {
          lane: 'memory',
          status: 'ready',
          label: 'memory_lane',
          detail: '1 mapped item(s)',
          detail_parts: [{ code: 'memory_mapped', params: { count: 1 } }],
        },
        {
          lane: 'cron',
          status: 'ready',
          label: 'cron_lane',
          detail: '2 scheduled task(s) will import paused; 1 skipped',
          detail_parts: [{ code: 'cron_importable', params: { importable: 2, skipped: 1 } }],
        },
      ],
    };

    render(
      <RealIntlPreviewStep
        source={{
          competitor: 'hermes',
          root: '/home/user/.hermes',
          confidence: 'high',
          files: [],
          memory_count_estimate: 1,
          skill_count: 0,
          has_api_keys: false,
        }}
        dryRun={withPluralLanes}
        importing={false}
        importSecrets={false}
        onImportSecretsChange={vi.fn()}
        importSessions
        onImportSessionsChange={vi.fn()}
        onConfirm={vi.fn()}
        onBack={vi.fn()}
      />,
    );

    expect(screen.getByText('1 mapped item')).toBeInTheDocument();
    expect(screen.getByText('2 scheduled tasks will import paused · 1 skipped')).toBeInTheDocument();
  });

  it('falls back to the raw detail line when no fragment is known', () => {
    const withUnknownPart: MemoryImportDryRunResponse = {
      ...dryRun,
      migration_lanes: [
        {
          lane: 'instruction',
          status: 'ready',
          label: 'instruction_lane',
          detail: 'future lane summary from a newer server',
          detail_parts: [{ code: 'instruction_future', params: { count: 1 } }],
        },
      ],
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
        }}
        dryRun={withUnknownPart}
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

    expect(screen.getByText('future lane summary from a newer server')).toBeInTheDocument();
  });

  it('lets the user skip imported chats and hides their preview when off', () => {
    const onImportSessionsChange = vi.fn();
    const withSessions: MemoryImportDryRunResponse = {
      ...dryRun,
      migration_lanes: [
        {
          lane: 'session',
          status: 'ready',
          label: 'session_lane',
          detail: '1 session(s) ready for resumption',
          detail_parts: [{ code: 'session_ready', params: { count: 1 } }],
        },
      ],
      session_preview: [
        {
          session_id: 'session-1',
          title: 'Debug the importer',
          turn_count: 2,
          tool_call_count: 1,
          source_platform: 'claude_code',
        },
      ],
    };

    render(
      <PreviewStep
        source={{
          competitor: 'claude',
          root: '/home/user/.claude',
          confidence: 'high',
          files: [],
          memory_count_estimate: 2,
          skill_count: 0,
          has_api_keys: false,
        }}
        dryRun={withSessions}
        importing={false}
        importSecrets={false}
        onImportSecretsChange={vi.fn()}
        importSessions={false}
        onImportSessionsChange={onImportSessionsChange}
        onConfirm={vi.fn()}
        onBack={vi.fn()}
        t={t}
      />,
    );

    const toggle = screen.getByTestId('migration-import-sessions');
    expect(toggle).not.toBeChecked();
    expect(screen.queryByText('Debug the importer')).toBeNull();
    expect(screen.getByText('Session Lane (Full Transcripts)')).toBeInTheDocument();
    expect(screen.getByText('not imported')).toBeInTheDocument();

    fireEvent.click(toggle);
    expect(onImportSessionsChange).toHaveBeenCalledWith(true);
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
