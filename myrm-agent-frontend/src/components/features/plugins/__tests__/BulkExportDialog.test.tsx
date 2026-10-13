/** @vitest-environment jsdom */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { AgentListItem } from '@/services/agent';
import type { ExpertExportPreview } from '@/services/expertPackage';
import BulkExportDialog from '../BulkExportDialog';

const { toastMock, previewMock, downloadMock, triggerDownloadMock } = vi.hoisted(() => ({
  toastMock: vi.fn(),
  previewMock: vi.fn(),
  downloadMock: vi.fn(),
  triggerDownloadMock: vi.fn(),
}));

// Resolve against the real en catalog so a missing or misnamed key fails here instead of rendering as a raw key.
vi.mock('next-intl', async () => {
  const { default: en } = await import('../../../../../locales/en.json');
  const resolve = (namespace: string | undefined, key: string): string | undefined => {
    const path = [...(namespace ? namespace.split('.') : []), ...key.split('.')];
    const hit = path.reduce<unknown>(
      (node, part) => (node && typeof node === 'object' ? (node as Record<string, unknown>)[part] : undefined),
      en,
    );
    return typeof hit === 'string' ? hit : undefined;
  };
  return {
    useTranslations: (namespace?: string) =>
      Object.assign(
        (key: string, values: Record<string, string | number> = {}) =>
          (resolve(namespace, key) ?? key).replace(/\{(\w+)\}/g, (_, name: string) => String(values[name] ?? '')),
        { has: (key: string) => resolve(namespace, key) !== undefined },
      ),
    useLocale: () => 'en',
  };
});

vi.mock('@/hooks/shared/useToast', () => ({ toast: toastMock }));

vi.mock('@/lib/utils/fileUtils', () => ({ triggerDownload: triggerDownloadMock }));

vi.mock('@/components/primitives/scroll-area', () => ({
  ScrollArea: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('@/services/expertPackage', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/expertPackage')>();
  return {
    ...actual,
    previewMultiExpertExport: previewMock,
    downloadMultiExpertPackage: downloadMock,
  };
});

const AGENTS: AgentListItem[] = [
  {
    id: 'agent-custom-1',
    name: 'Custom Agent 1',
    description: 'First custom agent',
    is_built_in: false,
    subagent_ids: ['sub-a', 'sub-b'],
    created_at: '1000',
    updated_at: '1000',
  },
  {
    id: 'agent-custom-2',
    name: 'Custom Agent 2',
    description: 'Second custom agent',
    is_built_in: false,
    created_at: '2000',
    updated_at: '2000',
  },
  {
    id: 'builtin:lead',
    name: 'Builtin Lead',
    description: 'System builtin agent',
    is_built_in: true,
    created_at: '3000',
    updated_at: '3000',
  },
];

function makePreview(overrides: Partial<ExpertExportPreview> = {}): ExpertExportPreview {
  return {
    plugin_name: 'multi-agents-bundle',
    version: '1.0.0',
    experts: [
      {
        name: 'Custom Agent 1',
        description: 'First custom agent',
        is_entry: true,
        skill_names: ['summarize'],
        connector_names: [],
        subagent_names: [],
        tool_names: [],
        recommended_model: null,
      },
      {
        name: 'Custom Agent 2',
        description: 'Second custom agent',
        is_entry: false,
        skill_names: ['summarize'],
        connector_names: [],
        subagent_names: [],
        tool_names: [],
        recommended_model: null,
      },
    ],
    skills: [{ name: 'summarize', source: 'custom', file_count: 2, version: '1.0.0', origin: null }],
    connectors: [],
    workspace_files: [],
    omitted: [],
    redactions: null,
    is_safe: true,
    review_digest: 'digest-bulk-123',
    package_bytes: 8192,
    build_error: null,
    ...overrides,
  };
}

describe('BulkExportDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('filters out builtin agents and selects all custom agents by default', () => {
    render(<BulkExportDialog open={true} onOpenChange={vi.fn()} agents={AGENTS} />);

    expect(screen.getByText('Custom Agent 1')).toBeDefined();
    expect(screen.getByText('Includes 2 sub-agent(s)')).toBeDefined();
    expect(screen.getByText('Custom Agent 2')).toBeDefined();
    expect(screen.queryByText('Builtin Lead')).toBeNull();
    expect(screen.getByText('2 / 2 selected')).toBeDefined();
  });

  it('allows unselecting and re-selecting agents', () => {
    render(<BulkExportDialog open={true} onOpenChange={vi.fn()} agents={AGENTS} />);

    const clearBtn = screen.getByText('Clear');
    fireEvent.click(clearBtn);
    expect(screen.getByText('0 / 2 selected')).toBeDefined();

    const selectAllBtn = screen.getByText('Select all');
    fireEvent.click(selectAllBtn);
    expect(screen.getByText('2 / 2 selected')).toBeDefined();
  });

  it('triggers preview and navigates to preview step on next button click', async () => {
    previewMock.mockResolvedValue(makePreview());

    render(<BulkExportDialog open={true} onOpenChange={vi.fn()} agents={AGENTS} />);

    const nextBtn = screen.getByText(/Next: analyze dependencies/);
    fireEvent.click(nextBtn);

    await waitFor(() => {
      expect(previewMock).toHaveBeenCalledWith({
        agentIds: ['agent-custom-1', 'agent-custom-2'],
        bundleName: undefined,
      });
    });

    await waitFor(() => {
      expect(screen.getByText(/multi-agents-bundle · v1.0.0/)).toBeDefined();
      expect(screen.getByText('Back')).toBeDefined();
    });
  });

  it('triggers export and download in preview step', async () => {
    const onOpenChange = vi.fn();
    const fakeBlob = new Blob(['zip-content']);
    previewMock.mockResolvedValue(makePreview());
    downloadMock.mockResolvedValue({ blob: fakeBlob, filename: 'multi-agents-bundle_v1.0.0.zip' });

    render(<BulkExportDialog open={true} onOpenChange={onOpenChange} agents={AGENTS} />);

    // 点击下一步进入预览
    fireEvent.click(screen.getByText(/Next: analyze dependencies/));

    await waitFor(() => {
      expect(screen.getByText('Export')).toBeDefined();
      expect(screen.getByText(/Migration guide: the ZIP carries a migration manifest/)).toBeDefined();
    });

    // 点击导出
    fireEvent.click(screen.getByText('Export'));

    await waitFor(() => {
      expect(downloadMock).toHaveBeenCalledWith({
        agentIds: ['agent-custom-1', 'agent-custom-2'],
        bundleName: undefined,
        applyRedactions: true,
        ignoredRedactions: {},
        reviewDigest: 'digest-bulk-123',
      });
      expect(triggerDownloadMock).toHaveBeenCalledWith(fakeBlob, 'multi-agents-bundle_v1.0.0.zip');
      expect(toastMock).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Agent package exported successfully',
          description: expect.stringContaining('Settings → Agents → Import'),
        }),
      );
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
  });
});
