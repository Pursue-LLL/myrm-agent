/** @vitest-environment jsdom */

vi.mock('next-intl', async (importOriginal) => {
  const actual = await importOriginal<typeof import('next-intl')>();
  return { ...actual, useLocale: () => 'en' };
});

import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import { describe, expect, it, vi } from 'vitest';

import type { CatchupBrief } from '@/services/chat';
import enMessages from '../../../../../../locales/en.json';
import { CatchupBriefCard } from '../CatchupBriefCard';

const brief = (overrides: Partial<CatchupBrief> = {}): CatchupBrief => ({
  chat_id: 'chat-1',
  chat_title: 'Quarterly report',
  updated_at: new Date().toISOString(),
  last_user_prompt: 'Summarise the report',
  result_preview: 'The report is ready.',
  files_touched: [],
  tool_counts: {},
  needs_from_user: null,
  status: 'completed',
  ...overrides,
});

function renderCard(value: CatchupBrief, onRead = vi.fn(), onNavigate = vi.fn()) {
  render(
    <NextIntlClientProvider locale="en" messages={{ Catchup: enMessages.Catchup }}>
      <CatchupBriefCard brief={value} onRead={onRead} onNavigate={onNavigate} />
    </NextIntlClientProvider>,
  );
  return { onRead, onNavigate };
}

describe('CatchupBriefCard', () => {
  it('shows what the user asked and the opening of the reply', () => {
    renderCard(brief());

    expect(screen.getByText('Summarise the report')).toBeInTheDocument();
    expect(screen.getByText('The report is ready.')).toBeInTheDocument();
    expect(screen.getByText('Completed')).toBeInTheDocument();
  });

  it.each([
    ['completed', 'Completed'],
    ['running', 'Running in Background'],
    ['waiting_for_approval', 'Waiting for Approval'],
    ['error', 'Error'],
    ['stopped', 'Stopped'],
  ] as const)('labels the %s status', (status, label) => {
    renderCard(brief({ status }));

    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it.each([
    ['approval', 'Waiting for your approval to continue.'],
    ['error', 'Stopped because of an error.'],
    ['question', 'Asked you a question.'],
  ] as const)('explains a %s need in the user language', (needs_from_user, text) => {
    renderCard(brief({ needs_from_user }));

    expect(screen.getByText(text)).toBeInTheDocument();
  });

  it('falls back to a localized title for an untitled chat', () => {
    renderCard(brief({ chat_title: '' }));

    expect(screen.getByText('Untitled conversation')).toBeInTheDocument();
  });

  it('summarises tools as a count instead of exposing tool identifiers', () => {
    renderCard(brief({ tool_counts: { file_edit_tool: 2, shell_tool: 1 } }));

    expect(screen.getByText('3 tool calls')).toBeInTheDocument();
    expect(screen.queryByText(/file_edit/)).not.toBeInTheDocument();
  });

  it('lists the first two files and counts the rest', () => {
    renderCard(brief({ files_touched: ['src/a.py', 'src/b.py', 'src/c.py', 'src/d.py'] }));

    expect(screen.getByText('a.py')).toBeInTheDocument();
    expect(screen.getByText('b.py')).toBeInTheDocument();
    expect(screen.queryByText('c.py')).not.toBeInTheDocument();
    expect(screen.getByText('+2 more')).toBeInTheDocument();
  });

  it.each(['running', 'waiting_for_approval'] as const)('offers no dismiss for a %s chat', (status) => {
    renderCard(brief({ status }));

    expect(screen.queryByRole('button', { name: 'Dismiss' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'View Chat' })).toBeInTheDocument();
  });

  it('reports dismiss and navigation with the chat id', () => {
    const { onRead, onNavigate } = renderCard(brief());

    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }));
    fireEvent.click(screen.getByRole('button', { name: 'View Chat' }));

    expect(onRead).toHaveBeenCalledWith('chat-1');
    expect(onNavigate).toHaveBeenCalledWith('chat-1');
  });
});
