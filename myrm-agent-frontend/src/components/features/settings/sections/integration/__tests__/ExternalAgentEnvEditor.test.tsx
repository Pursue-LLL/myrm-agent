/** @vitest-environment jsdom */
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

import type { ExternalAgentAuthMode } from '@/services/config';
import ExternalAgentEnvEditor from '../ExternalAgentEnvEditor';
import { newEnvRow, type EnvRow } from '../externalAgentModel';

function Harness({ initial = [], authMode = 'api_key' }: { initial?: EnvRow[]; authMode?: ExternalAgentAuthMode }) {
  const [rows, setRows] = useState<EnvRow[]>(initial);
  return (
    <>
      <ExternalAgentEnvEditor rows={rows} authMode={authMode} onChange={setRows} />
      <output data-testid="rows">{JSON.stringify(rows.map(({ name, value }) => [name, value]))}</output>
    </>
  );
}

const stored = () => JSON.parse(screen.getByTestId('rows').textContent ?? '[]') as [string, string][];

describe('ExternalAgentEnvEditor', () => {
  it('adds an empty line and puts the cursor in its name', async () => {
    render(<Harness />);

    await userEvent.click(screen.getByRole('button', { name: 'envAdd' }));

    const [name] = screen.getAllByLabelText('keyPlaceholder');
    expect(name).toHaveFocus();
    expect(stored()).toEqual([['', '']]);
  });

  it('takes what is typed as the name and the value of a line', async () => {
    render(<Harness />);
    await userEvent.click(screen.getByRole('button', { name: 'envAdd' }));

    await userEvent.type(screen.getByLabelText('keyPlaceholder'), 'ANTHROPIC_API_KEY');
    await userEvent.type(screen.getByLabelText('valuePlaceholder'), 'sk-secret');

    expect(stored()).toEqual([['ANTHROPIC_API_KEY', 'sk-secret']]);
  });

  it('masks values until they are shown, and says whether they are shown', async () => {
    render(<Harness initial={[newEnvRow('KEY', 'sk-secret')]} />);
    const value = screen.getByLabelText('valuePlaceholder');
    const toggle = screen.getByRole('button', { name: 'envShowValues' });

    expect(value).toHaveAttribute('type', 'password');
    expect(toggle).toHaveAttribute('aria-pressed', 'false');

    await userEvent.click(toggle);

    expect(value).toHaveAttribute('type', 'text');
    expect(toggle).toHaveAttribute('aria-pressed', 'true');
  });

  it('offers no show toggle while there is nothing to show', () => {
    render(<Harness />);

    expect(screen.queryByRole('button', { name: 'envShowValues' })).not.toBeInTheDocument();
  });

  it('keeps value fields away from the browser password manager', () => {
    render(<Harness initial={[newEnvRow('KEY', 'sk-secret')]} />);

    expect(screen.getByLabelText('valuePlaceholder')).toHaveAttribute('autocomplete', 'new-password');
  });

  it('removes only the line it belongs to', async () => {
    render(<Harness initial={[newEnvRow('A', '1'), newEnvRow('B', '2'), newEnvRow('C', '3')]} />);

    await userEvent.click(screen.getAllByRole('button', { name: 'envRemove' })[1]);

    expect(stored()).toEqual([
      ['A', '1'],
      ['C', '3'],
    ]);
  });

  it('points at a name that cannot be used', () => {
    render(<Harness initial={[newEnvRow('1BAD', 'v')]} />);

    expect(screen.getByText('envNameInvalid')).toBeInTheDocument();
    expect(screen.getByLabelText('keyPlaceholder')).toHaveAttribute('aria-invalid', 'true');
  });

  it('points at a value that has no name', () => {
    render(<Harness initial={[newEnvRow('', 'sk-1')]} />);

    expect(screen.getByText('envNameMissing')).toBeInTheDocument();
  });

  it('points at the second use of a name only', () => {
    render(<Harness initial={[newEnvRow('KEY', '1'), newEnvRow('KEY', '2')]} />);

    expect(screen.getAllByText('envNameDuplicate')).toHaveLength(1);
    const [first, second] = screen.getAllByLabelText('keyPlaceholder');
    expect(first).not.toHaveAttribute('aria-invalid');
    expect(second).toHaveAttribute('aria-invalid', 'true');
  });

  it('lets a blank line wait without complaint', () => {
    render(<Harness initial={[newEnvRow()]} />);

    expect(screen.queryByText(/^envName/)).not.toBeInTheDocument();
  });

  it.each([
    ['api_key', 'envHintApiKey'],
    ['subscription', 'envHintSubscription'],
  ] as const)('explains what the lines do while authentication is %s', (authMode, hint) => {
    render(<Harness authMode={authMode} />);

    expect(screen.getByText(hint)).toBeInTheDocument();
  });
});
