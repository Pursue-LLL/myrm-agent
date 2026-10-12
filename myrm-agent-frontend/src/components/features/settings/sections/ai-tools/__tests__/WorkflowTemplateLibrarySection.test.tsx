/** @vitest-environment jsdom */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  template: {
    template_id: 'tpl-1',
    display_name: 'Daily Digest',
    script_hash: 'hash-1',
    trust_latch: false,
    required_agent_types: [],
    placeholders: [],
    is_trunk: false,
    created_at: '2026-10-01T00:00:00Z',
    updated_at: '2026-10-02T00:00:00Z',
  },
  toast: vi.fn(),
  push: vi.fn(),
  submitRun: vi.fn(),
  t: (key: string) => key,
}));

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: mocks.push }) }));
vi.mock('next-intl', () => ({ useTranslations: () => mocks.t }));
vi.mock('@/hooks/shared/useToast', () => ({ useToast: () => ({ toast: mocks.toast }) }));
vi.mock('@/services/workflowTemplates', () => ({
  fetchWorkflowTemplates: vi.fn(async () => ({ templates: [mocks.template] })),
  fetchWorkflowTemplateDetail: vi.fn(),
  deleteWorkflowTemplate: vi.fn(),
  admitTemplateRun: vi.fn(async () => ({ admitted: true, reason_code: '' })),
}));
vi.mock('@/lib/workflow/useWorkflowTemplateTransfer', () => ({
  useWorkflowTemplateTransfer: () => ({
    importInputRef: { current: null },
    exportingTemplateId: null,
    importing: false,
    importOverwriteTarget: null,
    handleExport: vi.fn(),
    handleImportInputChange: vi.fn(),
    openImportPicker: vi.fn(),
    dismissImportOverwrite: vi.fn(),
    confirmImportOverwrite: vi.fn(),
  }),
}));
vi.mock('@/lib/workflow/submitWorkflowTemplateRun', () => ({
  submitWorkflowTemplateRun: (...args: unknown[]) => mocks.submitRun(...args),
}));
vi.mock('../WorkflowTemplateScriptPreview', () => ({ default: () => null }));
vi.mock('../WorkflowTemplateArgsDialog', () => ({ default: () => null }));
vi.mock('@/components/features/app-shell/confirm-dialog', () => ({ ConfirmDialog: () => null }));

import WorkflowTemplateLibrarySection from '../WorkflowTemplateLibrarySection';

async function runTemplateAndSettle(result: unknown): Promise<void> {
  mocks.submitRun.mockResolvedValueOnce(result);
  render(<WorkflowTemplateLibrarySection />);
  await screen.findByText('Daily Digest');
  fireEvent.change(screen.getByPlaceholderText('runQueryPlaceholder'), { target: { value: 'weekly numbers' } });

  const runButton = screen.getByRole('button', { name: 'run' });
  await act(async () => {
    fireEvent.click(runButton);
  });
  await waitFor(() => expect(mocks.submitRun).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(runButton).toBeEnabled());
}

describe('WorkflowTemplateLibrarySection run', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('opens the chat and confirms the start when the run was taken', async () => {
    await runTemplateAndSettle({ ok: true, chatId: 'chat-9' });

    expect(mocks.push).toHaveBeenCalledWith('/chat-9');
    expect(mocks.toast).toHaveBeenCalledWith({ title: 'runStarted', description: 'runStartedHint' });
  });

  it('stays on the page without a second notice when the chat refused the run and already said why', async () => {
    await runTemplateAndSettle({ ok: false, reason: 'refused' });

    expect(mocks.push).not.toHaveBeenCalled();
    expect(mocks.toast).not.toHaveBeenCalled();
  });

  it('reports a failed run', async () => {
    await runTemplateAndSettle({ ok: false, reason: 'error' });

    expect(mocks.push).not.toHaveBeenCalled();
    expect(mocks.toast).toHaveBeenCalledWith({ title: 'runFailed', variant: 'destructive' });
  });
});
