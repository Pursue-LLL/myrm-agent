/** @vitest-environment jsdom */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ExpertExportPreview } from '@/services/expertPackage';

import ExpertExportDialog from '../ExpertExportDialog';

const { toastMock, previewMock, downloadMock, triggerDownloadMock } = vi.hoisted(() => ({
  toastMock: vi.fn(),
  previewMock: vi.fn(),
  downloadMock: vi.fn(),
  triggerDownloadMock: vi.fn(),
}));

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('@/hooks/shared/useToast', () => ({ toast: toastMock }));

vi.mock('@/lib/utils/fileUtils', () => ({ triggerDownload: triggerDownloadMock }));

vi.mock('@/components/primitives/scroll-area', () => ({
  ScrollArea: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('@/services/expertPackage', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/expertPackage')>();
  return { ...actual, previewExpertExport: previewMock, downloadExpertPackage: downloadMock };
});

const FINDINGS = {
  'agents/report-lead.md': [
    { line_number: 3, original: 'token=sk-1', redacted: 'token=<REDACTED>', reason: 'API key' },
    { line_number: 9, original: 'password=abc', redacted: 'password=<REDACTED>', reason: 'Password' },
  ],
};

function makePreview(overrides: Partial<ExpertExportPreview> = {}): ExpertExportPreview {
  return {
    plugin_name: 'report-lead',
    version: '1.2.0',
    experts: [
      {
        name: 'Report Lead',
        description: 'Writes the weekly report',
        is_entry: true,
        skill_names: ['summarize'],
        connector_names: ['pdf'],
        subagent_names: [],
        tool_names: [],
        recommended_model: null,
      },
    ],
    skills: [{ name: 'summarize', source: 'custom', file_count: 2, version: '1.0.0', origin: null }],
    connectors: [{ name: 'pdf', type: 'http', secret_keys: ['PDF_API_KEY'] }],
    workspace_files: [],
    omitted: [{ kind: 'connector', name: 'local-tool', reason: 'local_path', owner: 'Report Lead' }],
    redactions: null,
    is_safe: true,
    review_digest: 'digest-1',
    package_bytes: 2048,
    build_error: null,
    ...overrides,
  };
}

function renderDialog(onOpenChange = vi.fn(), open = true) {
  render(<ExpertExportDialog agentId="agent-1" agentName="Report Lead" open={open} onOpenChange={onOpenChange} />);
  return onOpenChange;
}

async function readyToExport(name = 'actions.export') {
  const button = await screen.findByRole('button', { name });
  await waitFor(() => expect(button).toBeEnabled());
  return button;
}

describe('ExpertExportDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    previewMock.mockResolvedValue(makePreview());
    downloadMock.mockResolvedValue({ blob: new Blob(['zip']), filename: 'report-lead_v1.2.0.zip' });
  });

  it('does nothing until it is opened', () => {
    renderDialog(vi.fn(), false);

    expect(previewMock).not.toHaveBeenCalled();
  });

  it('shows what ships, what needs secrets and what stays behind', async () => {
    renderDialog();

    expect(await screen.findByText('report-lead · v1.2.0')).toBeInTheDocument();
    expect(screen.getByText('Report Lead', { selector: 'span' })).toBeInTheDocument();
    expect(screen.getByText('summarize')).toBeInTheDocument();
    expect(screen.getByText('pdf')).toBeInTheDocument();
    expect(screen.getByText('local-tool')).toBeInTheDocument();
    expect(screen.getByText('omitReason.local_path')).toBeInTheDocument();
    expect(screen.getByText('safeTitle')).toBeInTheDocument();
  });

  it('exports with the digest the server issued and closes on success', async () => {
    const onOpenChange = renderDialog();

    fireEvent.click(await readyToExport());

    await waitFor(() =>
      expect(downloadMock).toHaveBeenCalledWith({
        agentId: 'agent-1',
        applyRedactions: true,
        ignoredRedactions: {},
        reviewDigest: 'digest-1',
      }),
    );
    expect(triggerDownloadMock).toHaveBeenCalledWith(expect.any(Blob), 'report-lead_v1.2.0.zip');
    expect(toastMock).toHaveBeenCalledWith(expect.objectContaining({ title: 'exportSuccess' }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('names the file after the package when the server sends no filename', async () => {
    downloadMock.mockResolvedValue({ blob: new Blob(['zip']), filename: null });
    renderDialog();

    fireEvent.click(await readyToExport());

    await waitFor(() => expect(triggerDownloadMock).toHaveBeenCalledWith(expect.any(Blob), 'report-lead_v1.2.0.zip'));
  });

  it('exports redacted by default and sends only the findings the author kept', async () => {
    previewMock.mockResolvedValue(makePreview({ redactions: FINDINGS, is_safe: false }));
    renderDialog();
    await readyToExport('actions.exportRedacted');

    // Boxes: [file toggle, finding 0, finding 1]; unchecking finding 1 keeps its text.
    fireEvent.click(screen.getAllByRole('checkbox')[2]);
    fireEvent.click(screen.getByRole('button', { name: 'actions.exportRedacted' }));

    await waitFor(() =>
      expect(downloadMock).toHaveBeenCalledWith({
        agentId: 'agent-1',
        applyRedactions: true,
        ignoredRedactions: { 'agents/report-lead.md': [1] },
        reviewDigest: 'digest-1',
      }),
    );
  });

  it('exports the original only as an explicit decision on every finding', async () => {
    previewMock.mockResolvedValue(makePreview({ redactions: FINDINGS, is_safe: false }));
    renderDialog();
    await readyToExport('actions.exportRedacted');

    fireEvent.click(screen.getByRole('button', { name: 'actions.exportOriginal' }));

    await waitFor(() =>
      expect(downloadMock).toHaveBeenCalledWith({
        agentId: 'agent-1',
        applyRedactions: false,
        ignoredRedactions: { 'agents/report-lead.md': [0, 1] },
        reviewDigest: 'digest-1',
      }),
    );
  });

  it('does not offer the original when there is nothing to review', async () => {
    renderDialog();
    await readyToExport();

    expect(screen.queryByRole('button', { name: 'actions.exportOriginal' })).not.toBeInTheDocument();
  });

  it('re-reviews when the agent changed after the preview', async () => {
    const { ExpertExportError } = await import('@/services/expertPackage');
    downloadMock.mockRejectedValue(new ExpertExportError('changed', 'export_changed_since_preview'));
    const onOpenChange = renderDialog();

    fireEvent.click(await readyToExport());

    await waitFor(() => expect(previewMock).toHaveBeenCalledTimes(2));
    expect(toastMock).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'changedSinceReview', variant: 'destructive' }),
    );
    expect(triggerDownloadMock).not.toHaveBeenCalled();
    expect(onOpenChange).not.toHaveBeenCalled();
  });

  it('keeps the dialog open and explains a refused export', async () => {
    downloadMock.mockRejectedValue(new Error('Package is too large'));
    const onOpenChange = renderDialog();

    fireEvent.click(await readyToExport());

    await waitFor(() =>
      expect(toastMock).toHaveBeenCalledWith(
        expect.objectContaining({ title: 'exportFailed', description: 'Package is too large', variant: 'destructive' }),
      ),
    );
    expect(onOpenChange).not.toHaveBeenCalled();
    // The author can try again.
    expect(screen.getByRole('button', { name: 'actions.export' })).toBeEnabled();
  });

  it('refuses an export that could not even be built', async () => {
    previewMock.mockResolvedValue(
      makePreview({ build_error: 'Package exceeds the size limit', redactions: FINDINGS, is_safe: false }),
    );
    renderDialog();

    expect(await screen.findByText('buildErrorTitle')).toBeInTheDocument();
    expect(screen.getByText('Package exceeds the size limit')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'actions.exportRedacted' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'actions.exportOriginal' })).not.toBeInTheDocument();
  });

  it('reports a preview failure and offers no export', async () => {
    previewMock.mockRejectedValue(new Error('Agent not found'));
    renderDialog();

    expect(await screen.findByText('previewFailed')).toBeInTheDocument();
    expect(screen.getByText('Agent not found')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'actions.export' })).not.toBeInTheDocument();
  });
});
