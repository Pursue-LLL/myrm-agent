/** @vitest-environment jsdom */
/**
 * [INPUT]
 * ../PreviewStep (POS: 迁移向导预览步骤)
 * ../PreviewCards (POS: 预览常显卡片，导出车道碎片码表 LANE_DETAIL_CODES)
 * ./wizardTestKit (POS: 迁移向导测试共用夹具)
 * @/test-utils/realIntl (POS: 基于真实语言包的翻译层)
 * ../../../../../../../../locales/en.json (POS: 英文文案 SSOT)
 *
 * [OUTPUT]
 * 预览页迁移车道的回归测试。
 *
 * [POS]
 * 车道详情按服务端 detail_parts 本地化（含复数，走真实翻译器），语言包覆盖全部已知碎片码，
 * 未知碎片回退为服务端原文；历史会话车道可由用户跳过，关闭时不展示会话预览。
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { useTranslations } from 'next-intl';
import { afterEach, describe, expect, it, vi } from 'vitest';

import en from '../../../../../../../../locales/en.json';
import type { MemoryImportDryRunResponse } from '@/services/memory/archive';
import { LANE_DETAIL_CODES } from '../PreviewCards';
import { PreviewStep } from '../PreviewStep';
import { dryRun, t } from './wizardTestKit';

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'en'));

function RealIntlPreviewStep(props: Omit<Parameters<typeof PreviewStep>[0], 't'>) {
  const t = useTranslations('memory.migrationWizard');
  return <PreviewStep {...props} t={t} />;
}

describe('migration wizard preview lanes', () => {
  afterEach(cleanup);

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
          can_import_secrets: false,
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
          can_import_secrets: false,
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
          can_import_secrets: false,
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
          can_import_secrets: false,
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
});
