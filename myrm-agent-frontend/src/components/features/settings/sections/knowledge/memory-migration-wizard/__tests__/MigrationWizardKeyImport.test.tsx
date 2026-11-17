/** @vitest-environment jsdom */
/**
 * [INPUT]
 * ../PreviewStep (POS: 迁移向导预览步骤)
 * ../SecretsImportNotice (POS: 迁移向导密钥导入结果提示)
 * @/test-utils/realIntl (POS: 基于真实语言包的翻译层)
 *
 * [OUTPUT]
 * 密钥导入 opt-in 的回归测试：何时提供勾选、缺少服务商时的提示、结果页如何列出未导入的变量名。
 *
 * [POS]
 * 迁移向导密钥导入测试。断言勾选框只在来源真有可导入的 .env 密钥时出现，且提示与能否导入一致；
 * 结果页按原因分组列出未导入的变量名，中英文案都走真实语言包，页面上不出现任何密钥值。
 */
import type { ReactNode } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import en from '../../../../../../../../locales/en.json';
import zh from '../../../../../../../../locales/zh.json';

const intl = vi.hoisted(() => ({ locale: 'en' as 'en' | 'zh' }));

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => intl.locale));
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

import { useTranslations } from 'next-intl';

import type { MemoryImportDryRunResponse } from '@/services/memory/archive';
import type { ExternalSource, SecretsImportResponse } from '@/services/migrationDiscovery';
import { PreviewStep } from '../PreviewStep';
import { SecretsImportNotice } from '../SecretsImportNotice';

const LOCALES = ['en', 'zh'] as const;
const bundles = { en, zh };
const wizardCopy = (locale: (typeof LOCALES)[number]) => bundles[locale].memory.migrationWizard;

const source = (overrides: Partial<ExternalSource> = {}): ExternalSource => ({
  competitor: 'hermes',
  root: '/home/user/.hermes',
  confidence: 'high',
  files: [],
  memory_count_estimate: 2,
  skill_count: 0,
  has_api_keys: true,
  can_import_secrets: true,
  ...overrides,
});

const dryRun = (overrides: Partial<MemoryImportDryRunResponse> = {}): MemoryImportDryRunResponse => ({
  dry_run_id: 'memory-import:test',
  payload_hash: 'hash',
  expires_at: '2026-01-02T01:00:00Z',
  result: {
    summary: { source: 'hermes', version: '1', total_items: 1, mapped_items: 1, unmapped_items: 0, status: 'ready' },
    mappings: [],
    warnings: [],
    normalized_data: {},
  },
  pending_skills: [],
  pending_skills_total: 0,
  coverage_items: [],
  migration_lanes: [],
  ...overrides,
});

function WizardPreview(props: Omit<Parameters<typeof PreviewStep>[0], 't'>) {
  const t = useTranslations('memory.migrationWizard');
  return <PreviewStep {...props} t={t} />;
}

function WizardNotice({ result }: { result: SecretsImportResponse | null }) {
  const t = useTranslations('memory.migrationWizard');
  return <SecretsImportNotice result={result} t={t} />;
}

const renderPreview = (
  overrides: { source?: Partial<ExternalSource>; dryRun?: Partial<MemoryImportDryRunResponse> } = {},
) => {
  const onImportSecretsChange = vi.fn();
  render(
    <WizardPreview
      source={source(overrides.source)}
      dryRun={dryRun(overrides.dryRun)}
      importing={false}
      importSecrets={false}
      onImportSecretsChange={onImportSecretsChange}
      importSessions
      onImportSessionsChange={vi.fn()}
      onConfirm={vi.fn()}
      onBack={vi.fn()}
    />,
  );
  return { onImportSecretsChange };
};

describe.each(LOCALES)('migration wizard key import (%s)', (locale) => {
  const copy = wizardCopy(locale);

  afterEach(cleanup);

  const setLocale = () => {
    intl.locale = locale;
  };

  it('offers the key import when the source holds keys the import can bring', () => {
    setLocale();
    const { onImportSecretsChange } = renderPreview();

    const tick = screen.getByRole('checkbox', { name: copy.preview.importSecretsLabel });
    fireEvent.click(tick);

    expect(onImportSecretsChange).toHaveBeenCalledExactlyOnceWith(true);
  });

  it('does not offer the key import for keys that only live in an auth file', () => {
    setLocale();
    renderPreview({ source: { has_api_keys: true, can_import_secrets: false } });

    expect(screen.queryByRole('checkbox', { name: copy.preview.importSecretsLabel })).toBeNull();
  });

  it('points at the key import only when the import could create the missing providers', () => {
    setLocale();
    renderPreview({ dryRun: { providers_configured: false } });

    expect(screen.getByText(copy.preview.providersMissingImportableHint)).toBeInTheDocument();
    expect(screen.queryByText(copy.preview.providersMissingHint)).toBeNull();

    cleanup();
    renderPreview({ source: { can_import_secrets: false }, dryRun: { providers_configured: false } });

    expect(screen.getByText(copy.preview.providersMissingHint)).toBeInTheDocument();
    expect(screen.queryByText(copy.preview.providersMissingImportableHint)).toBeNull();
  });

  it('renders nothing before the key import has run', () => {
    setLocale();
    const { container } = render(<WizardNotice result={null} />);

    expect(container).toBeEmptyDOMElement();
  });

  it('reports what was imported and lists the keys left alone by reason, names only', () => {
    setLocale();
    render(
      <WizardNotice
        result={{
          imported_keys: ['OPENAI_API_KEY', 'GROQ_API_KEY'],
          skipped_keys: [
            { name: 'MINIMAX_API_KEY', reason: 'needs_endpoint' },
            { name: 'GLM_API_KEY', reason: 'needs_endpoint' },
            { name: 'COHERE_API_KEY', reason: 'unsupported' },
          ],
        }}
      />,
    );

    expect(screen.getByText(copy.secretsImportSuccess.replace('{count}', '2'))).toBeInTheDocument();
    expect(
      screen.getByText(copy.result.secretsNeedEndpoint.replace('{names}', 'MINIMAX_API_KEY, GLM_API_KEY')),
    ).toBeInTheDocument();
    expect(screen.getByText(copy.result.secretsUnsupported.replace('{names}', 'COHERE_API_KEY'))).toBeInTheDocument();
  });

  it('says only what needs manual setup when nothing could be imported', () => {
    setLocale();
    const { container } = render(
      <WizardNotice
        result={{ imported_keys: [], skipped_keys: [{ name: 'KIMI_API_KEY', reason: 'needs_endpoint' }] }}
      />,
    );

    expect(container.querySelectorAll('p')).toHaveLength(1);
    expect(screen.getByText(copy.result.secretsNeedEndpoint.replace('{names}', 'KIMI_API_KEY'))).toBeInTheDocument();
  });

  it('keeps the endpoint advice off keys that no provider takes', () => {
    setLocale();
    const { container } = render(
      <WizardNotice
        result={{ imported_keys: [], skipped_keys: [{ name: 'COHERE_API_KEY', reason: 'unsupported' }] }}
      />,
    );

    expect(container.querySelectorAll('p')).toHaveLength(1);
    expect(screen.getByText(copy.result.secretsUnsupported.replace('{names}', 'COHERE_API_KEY'))).toBeInTheDocument();
  });

  it('stays quiet about a key import that skipped nothing', () => {
    setLocale();
    const { container } = render(<WizardNotice result={{ imported_keys: ['OPENAI_API_KEY'], skipped_keys: [] }} />);

    expect(container.querySelectorAll('p')).toHaveLength(1);
    expect(screen.getByText(copy.secretsImportSuccess.replace('{count}', '1'))).toBeInTheDocument();
  });
});
