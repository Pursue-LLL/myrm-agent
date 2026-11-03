/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ExecutionTrace } from '@/services/statistics';
import type { MockLocale } from '@/test-utils/realIntl';

const { intl, writeToClipboard, triggerDownload } = vi.hoisted(() => ({
  intl: { locale: 'en' as MockLocale },
  writeToClipboard: vi.fn().mockResolvedValue(true),
  triggerDownload: vi.fn().mockResolvedValue(true),
}));

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => intl.locale));
vi.mock('@/lib/utils/clipboardUtils', () => ({ writeToClipboard }));
vi.mock('@/lib/utils/fileUtils', async () => ({
  ...(await vi.importActual<typeof import('@/lib/utils/fileUtils')>('@/lib/utils/fileUtils')),
  triggerDownload,
}));

import { ProjectExperienceWizardModal } from '../ProjectExperienceWizardModal';

const trace: ExecutionTrace = {
  session_id: 'sess-wizard-1',
  metadata: { user_id: null, agent_id: 'agent-1', task_type: null, trace_id: null },
  outcome: 'success',
  start_time: 1000,
  end_time: 1050,
  duration_ms: 50000,
  task_input: 'Refactor the sync module',
  output: 'Done',
  tool_calls: [],
  llm_calls: [],
  errors: [],
  human_feedback: [],
  total_events: 1,
  total_tokens: 1200,
};

function renderModal() {
  return render(<ProjectExperienceWizardModal trace={trace} isOpen onClose={vi.fn()} />);
}

describe('ProjectExperienceWizardModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    intl.locale = 'en';
  });

  it('shows the wizard chrome and generated steps in English', () => {
    renderModal();

    expect(screen.getByText('Six-step project experience wizard')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Export Markdown/ })).toBeInTheDocument();
    expect(screen.getByTitle('Download JSON')).toBeInTheDocument();
    expect(screen.getByText('Requirements')).toBeInTheDocument();
    expect(screen.getByText('Original requirements')).toBeInTheDocument();
    expect(screen.getByText('Key facts and evidence:')).toBeInTheDocument();
    expect(screen.getByText('Step 1 / 6')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled();
  });

  it('shows the wizard chrome and generated steps in Chinese', () => {
    intl.locale = 'zh';
    renderModal();

    expect(screen.getByText('项目实战六步经验向导')).toBeInTheDocument();
    expect(screen.getByText('原始需求输入')).toBeInTheDocument();
    expect(screen.getByText('关键事实与实证记录：')).toBeInTheDocument();
    expect(screen.getByText('步骤 1 / 6')).toBeInTheDocument();
    expect(screen.queryByText(/Evidence Pack Wizard/)).not.toBeInTheDocument();
  });

  it('walks through the steps with the localized navigation buttons', () => {
    renderModal();

    fireEvent.click(screen.getByRole('button', { name: 'Next' }));

    expect(screen.getByText('Step 2 / 6')).toBeInTheDocument();
    expect(screen.getByText('Architecture and decisions')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Previous' })).toBeEnabled();
  });

  it('copies a Markdown pack written in the interface language', async () => {
    renderModal();

    fireEvent.click(screen.getByTitle('Copy Markdown'));

    await waitFor(() => expect(screen.getByText('Copied')).toBeInTheDocument());
    const [markdown] = writeToClipboard.mock.calls[0] as [string];
    expect(markdown).toContain('# Project experience evidence pack (six steps): Refactor the sync module');
    expect(markdown).toContain('## Step 1: Original requirements');
  });

  it('downloads the Markdown pack in Chinese when the interface is Chinese', () => {
    intl.locale = 'zh';
    renderModal();

    fireEvent.click(screen.getByTitle('下载 Markdown'));

    expect(triggerDownload).toHaveBeenCalledTimes(1);
  });
});
