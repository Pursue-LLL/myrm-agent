/** @vitest-environment jsdom */
/**
 * [INPUT]
 * - ../KanbanTaskHandoffSection (real, with the real next-intl translator of the `kanban` namespace)
 * - locales/{en,zh,zh-TW,ja,ko,de}.json (real copy)
 *
 * [OUTPUT]
 * - Test suite proving the handoff section renders translated copy, never a raw key path, in every locale
 *
 * [POS]
 * The section receives its translator as a prop, so the static i18n gate cannot resolve its keys. A missing key
 * renders as "kanban.<key>" there, and the stub translator of the behaviour suite hides that; this suite fails on it.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { NextIntlClientProvider, useTranslations } from 'next-intl';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { KanbanTask } from '@/services/kanban';
import { toast } from 'sonner';
import { KanbanTaskHandoffSection } from '../KanbanTaskHandoffSection';
import de from '../../../../../locales/de.json';
import en from '../../../../../locales/en.json';
import ja from '../../../../../locales/ja.json';
import ko from '../../../../../locales/ko.json';
import zhTW from '../../../../../locales/zh-TW.json';
import zh from '../../../../../locales/zh.json';

// The global setup stubs next-intl with an identity translator; this suite asserts the real locale copy.
vi.mock('next-intl', async (importOriginal) => importOriginal<typeof import('next-intl')>());

const mockMoveTask = vi.fn();
vi.mock('@/services/kanban', () => ({
  moveTask: (...args: unknown[]) => mockMoveTask(...args),
}));

vi.mock('@/store/useAgentStore', () => ({
  default: (selector: (state: { agents: Array<{ id: string; name: string }> }) => unknown) =>
    selector({
      agents: [
        { id: 'agent-dev', name: 'Developer Agent' },
        { id: 'agent-qa', name: 'QA Engineer' },
      ],
    }),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const LOCALES = { en, zh, 'zh-TW': zhTW, ja, ko, de } as const;
type LocaleCode = keyof typeof LOCALES;

const task = {
  task_id: 'task-101',
  title: 'Implement OAuth Token Revocation',
  status: 'backlog',
  agent_id: 'agent-dev',
  metadata: {
    handoff_history: [{ from_agent_id: null, to_agent_id: null, summary: 'Spec done', changed_files: ['a.py'] }],
  },
} as unknown as KanbanTask;

const Harness = () => {
  const t = useTranslations('kanban');
  return <KanbanTaskHandoffSection task={task} onChanged={vi.fn()} t={t} />;
};

const renderSection = (locale: LocaleCode) =>
  render(
    <NextIntlClientProvider locale={locale} messages={{ kanban: LOCALES[locale].kanban }}>
      <Harness />
    </NextIntlClientProvider>,
  );

describe.each(Object.keys(LOCALES) as LocaleCode[])('Kanban handoff section (%s)', (locale) => {
  const copy = LOCALES[locale].kanban;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows the translated header, assignee bar and history, with no raw key path', () => {
    const { container } = renderSection(locale);

    expect(screen.getByText(copy.taskHandoff)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: new RegExp(copy.delegateTask) })).toBeInTheDocument();
    expect(screen.getByText(`${copy.currentAssignee}:`)).toBeInTheDocument();
    expect(screen.getByText(new RegExp(`^${copy.handoffTimeline}`))).toBeInTheDocument();
    // The history record has no from/to agent: both ends fall back to the translated placeholders.
    expect(screen.getByText(copy.unassigned)).toBeInTheDocument();
    expect(screen.getByText(copy.unknown)).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/kanban\.[A-Za-z]/);
  });

  it('shows every form label, status option and button in the expanded form', () => {
    const { container } = renderSection(locale);
    fireEvent.click(screen.getByRole('button', { name: new RegExp(copy.delegateTask) }));

    expect(screen.getByText(copy.collapse)).toBeInTheDocument();
    expect(screen.getByText(copy.transferToAgent)).toBeInTheDocument();
    expect(screen.getByRole('option', { name: copy.selectAgentPlaceholder })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: `Developer Agent (${copy.current})` })).toBeInTheDocument();
    expect(screen.getByText(copy.targetStatus)).toBeInTheDocument();
    for (const status of [copy.statusReady, copy.statusBacklog, copy.statusInReview]) {
      expect(screen.getByRole('option', { name: status })).toBeInTheDocument();
    }
    expect(screen.getByText(copy.handoffSummary)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(copy.handoffSummaryPlaceholder)).toBeInTheDocument();
    expect(screen.getByText(copy.changedFilesMetadata)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: copy.cancel })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: new RegExp(copy.confirmHandoff) })).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/kanban\.[A-Za-z]/);
  });

  it('toasts the translated success message after a handoff', async () => {
    mockMoveTask.mockResolvedValueOnce({ success: true });
    renderSection(locale);
    fireEvent.click(screen.getByRole('button', { name: new RegExp(copy.delegateTask) }));
    fireEvent.change(screen.getAllByRole('combobox')[0], { target: { value: 'agent-qa' } });
    fireEvent.click(screen.getByRole('button', { name: new RegExp(copy.confirmHandoff) }));

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith(copy.handoffSuccess));
  });

  it('toasts the translated failure message when the server gives no reason', async () => {
    mockMoveTask.mockRejectedValueOnce(new Error(''));
    renderSection(locale);
    fireEvent.click(screen.getByRole('button', { name: new RegExp(copy.delegateTask) }));
    fireEvent.change(screen.getAllByRole('combobox')[0], { target: { value: 'agent-qa' } });
    fireEvent.click(screen.getByRole('button', { name: new RegExp(copy.confirmHandoff) }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(copy.handoffFailed));
  });
});
