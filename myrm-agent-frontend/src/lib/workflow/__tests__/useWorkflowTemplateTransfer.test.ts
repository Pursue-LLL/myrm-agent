import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, type RenderHookResult } from '@testing-library/react';
import type { ChangeEvent } from 'react';

import { useWorkflowTemplateTransfer } from '@/lib/workflow/useWorkflowTemplateTransfer';
import type { WorkflowTemplateSummary } from '@/services/workflowTemplates';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const mockUpsert = vi.fn();
const mockReload = vi.fn();

vi.mock('@/services/workflowTemplates', () => ({
  upsertWorkflowTemplate: (...args: unknown[]) => mockUpsert(...args),
}));

const EXISTING_TEMPLATE: WorkflowTemplateSummary = {
  template_id: 'weekly-sales',
  display_name: 'Weekly Sales',
  script_hash: 'abc',
  trust_latch: true,
  required_agent_types: ['generalPurpose'],
  placeholders: [],
  created_at: '2026-08-06T00:00:00.000Z',
  updated_at: '2026-08-06T00:00:00.000Z',
};

function buildImportFile(templateId: string, displayName: string): File {
  return new File(
    [
      JSON.stringify({
        version: '1',
        template: {
          templateId,
          displayName,
          scriptCode: 'import myrm_tools',
          trustLatch: true,
        },
      }),
    ],
    `${templateId}.myrm-workflow.json`,
    { type: 'application/json' },
  );
}

function importFile(
  hook: RenderHookResult<ReturnType<typeof useWorkflowTemplateTransfer>, unknown>,
  file: File,
) {
  return act(async () => {
    await hook.result.current.handleImportInputChange({
      target: { files: [file], value: '' },
    } as unknown as ChangeEvent<HTMLInputElement>);
  });
}

describe('useWorkflowTemplateTransfer', () => {
  const toast = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    mockReload.mockResolvedValue(undefined);
  });

  it('opens overwrite dialog instead of upserting when template id already exists', async () => {
    const hook = renderHook(() =>
      useWorkflowTemplateTransfer({
        templates: [EXISTING_TEMPLATE],
        reloadTemplates: mockReload,
        toast,
      }),
    );

    await importFile(hook, buildImportFile('weekly-sales', 'Weekly Sales'));

    expect(mockUpsert).not.toHaveBeenCalled();
    expect(hook.result.current.importOverwriteTarget).toEqual({
      templateId: 'weekly-sales',
      displayName: 'Weekly Sales',
      scriptCode: 'import myrm_tools',
      trustLatch: true,
    });
  });

  it('confirmImportOverwrite throws on upsert failure and keeps overwrite target', async () => {
    mockUpsert.mockRejectedValue(new Error('upsert failed'));

    const hook = renderHook(() =>
      useWorkflowTemplateTransfer({
        templates: [EXISTING_TEMPLATE],
        reloadTemplates: mockReload,
        toast,
      }),
    );

    await importFile(hook, buildImportFile('weekly-sales', 'Weekly Sales'));

    await expect(async () => {
      await act(async () => {
        await hook.result.current.confirmImportOverwrite();
      });
    }).rejects.toThrow('upsert failed');

    expect(toast).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'importFailed', variant: 'destructive' }),
    );
    expect(hook.result.current.importOverwriteTarget).not.toBeNull();
    expect(mockReload).not.toHaveBeenCalled();
  });

  it('confirmImportOverwrite clears overwrite target after success', async () => {
    mockUpsert.mockResolvedValue(EXISTING_TEMPLATE);

    const hook = renderHook(() =>
      useWorkflowTemplateTransfer({
        templates: [EXISTING_TEMPLATE],
        reloadTemplates: mockReload,
        toast,
      }),
    );

    await importFile(hook, buildImportFile('weekly-sales', 'Weekly Sales Updated'));

    await act(async () => {
      await hook.result.current.confirmImportOverwrite();
    });

    expect(mockUpsert).toHaveBeenCalledTimes(1);
    expect(mockReload).toHaveBeenCalledTimes(1);
    expect(hook.result.current.importOverwriteTarget).toBeNull();
  });

  it('imports a new template without overwrite dialog', async () => {
    mockUpsert.mockResolvedValue({
      ...EXISTING_TEMPLATE,
      template_id: 'new-template',
    });

    const hook = renderHook(() =>
      useWorkflowTemplateTransfer({
        templates: [],
        reloadTemplates: mockReload,
        toast,
      }),
    );

    await importFile(hook, buildImportFile('new-template', 'New Template'));

    expect(mockUpsert).toHaveBeenCalledWith('new-template', {
      display_name: 'New Template',
      script_code: 'import myrm_tools',
      trust_latch: true,
    });
    expect(mockReload).toHaveBeenCalledTimes(1);
    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ title: 'importSuccess' }));
  });
});
