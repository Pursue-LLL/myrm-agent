/** @vitest-environment jsdom */
'use client';

import { useState } from 'react';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { SWRConfig } from 'swr';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { findBindingIssues } from '@/lib/utils/agent-config';
import type { CommandBindingConfig } from '@/services/agent';

const { listSkillsMock } = vi.hoisted(() => ({ listSkillsMock: vi.fn() }));

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({ useTranslations: () => stableT }));
vi.mock('@/services/skill', () => ({ listSkills: listSkillsMock }));

import { CommandBindingsEditor } from '../CommandBindingsEditor';

function Harness({ initial = [] }: { initial?: CommandBindingConfig[] }) {
  const [value, setValue] = useState(initial);
  return (
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <CommandBindingsEditor value={value} issues={findBindingIssues(value)} onChange={setValue} />
      <output data-testid="value">{JSON.stringify(value)}</output>
    </SWRConfig>
  );
}

const currentValue = (): CommandBindingConfig[] => JSON.parse(screen.getByTestId('value').textContent ?? '[]');

const binding = (overrides: Partial<CommandBindingConfig> = {}): CommandBindingConfig => ({
  command_name: 'report',
  skill_ids: ['skill-a'],
  ...overrides,
});

const expandRow = (name: RegExp) => fireEvent.click(screen.getByRole('button', { name }));

describe('CommandBindingsEditor', () => {
  beforeEach(() => {
    listSkillsMock.mockResolvedValue({
      skills: [
        { id: 'skill-a', name: 'Research' },
        { id: 'skill-b', name: 'Writer' },
      ],
    });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('shows the empty state and adds an expanded blank row without nagging about it', async () => {
    render(<Harness />);
    expect(screen.getByText('empty')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'add' }));

    expect(screen.queryByText('empty')).toBeNull();
    expect(screen.getByLabelText('nameLabel')).toBeTruthy();
    expect(screen.queryByText('issueIncomplete')).toBeNull();
    expect(currentValue()).toEqual([
      { command_name: '', skill_ids: [], description: '', aliases: [], instruction: '' },
    ]);
    await screen.findByRole('button', { name: 'Research' });
  });

  it('keeps only slash-safe characters in the command name', async () => {
    render(<Harness initial={[binding({ command_name: '' })]} />);
    expandRow(/\/…/);

    fireEvent.change(screen.getByLabelText('nameLabel'), { target: { value: 'Daily Report! 日报' } });

    expect(currentValue()[0].command_name).toBe('DailyReport');
  });

  it('toggles skills and reveals the bundle instruction once several are selected', async () => {
    render(<Harness initial={[binding()]} />);
    expandRow(/\/report/);
    expect(screen.queryByLabelText('instructionLabel')).toBeNull();

    fireEvent.click(await screen.findByRole('button', { name: 'Writer' }));

    expect(currentValue()[0].skill_ids).toEqual(['skill-a', 'skill-b']);
    expect(screen.getByRole('button', { name: 'Writer' }).getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByLabelText('instructionLabel')).toBeTruthy();
    expect(screen.getAllByText('bundle').length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole('button', { name: 'Research' }));
    expect(currentValue()[0].skill_ids).toEqual(['skill-b']);
    expect(screen.queryByLabelText('instructionLabel')).toBeNull();
  });

  it('flags a row left incomplete once it is collapsed', async () => {
    render(<Harness initial={[binding({ skill_ids: [] })]} />);

    expect(screen.getByText('issueIncomplete')).toBeTruthy();
    expandRow(/\/report/);
    expect(screen.queryByText('issueIncomplete')).toBeNull();
  });

  it('flags every row that shares a command name or alias', () => {
    render(
      <Harness
        initial={[
          binding({ aliases: ['dr'] }),
          binding({ command_name: 'daily', aliases: ['DR'] }),
          binding({ command_name: 'solo' }),
        ]}
      />,
    );

    expect(screen.getAllByText('issueDuplicate')).toHaveLength(2);
  });

  it('lets the alias field hold a trailing comma while committing only clean aliases', () => {
    render(<Harness initial={[binding()]} />);
    expandRow(/\/report/);
    const input = screen.getByLabelText('aliasesLabel') as HTMLInputElement;

    fireEvent.change(input, { target: { value: 'dr, rep ort,' } });
    expect(input.value).toBe('dr, rep ort,');
    expect(currentValue()[0].aliases).toEqual(['dr', 'report']);

    fireEvent.blur(input);
    expect(input.value).toBe('dr, report');
  });

  it('removes a row and collapses the editor', () => {
    render(<Harness initial={[binding(), binding({ command_name: 'second' })]} />);
    expandRow(/\/second/);

    const row = screen.getByRole('button', { name: /\/second/ }).closest('div')?.parentElement as HTMLElement;
    fireEvent.click(within(row).getByRole('button', { name: 'remove' }));

    expect(currentValue().map((item) => item.command_name)).toEqual(['report']);
    expect(screen.queryByLabelText('nameLabel')).toBeNull();
  });

  it('keeps a skill that no longer exists selectable so it can be dropped', async () => {
    render(<Harness initial={[binding({ skill_ids: ['skill-a', 'gone'] })]} />);
    expandRow(/\/report/);

    fireEvent.click(await screen.findByRole('button', { name: 'gone' }));

    expect(currentValue()[0].skill_ids).toEqual(['skill-a']);
    await waitFor(() => expect(screen.queryByRole('button', { name: 'gone' })).toBeNull());
  });
});
