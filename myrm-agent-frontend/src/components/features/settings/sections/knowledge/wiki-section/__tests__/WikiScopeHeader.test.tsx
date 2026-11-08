/** @vitest-environment jsdom */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { click, resetKit, world } from './wikiSectionTestKit';
import { agentOf } from './wikiSectionFixtures';
import { WikiScopeHeader } from '../WikiScopeHeader';

const AGENTS = [agentOf('a1', 'Alpha'), agentOf('a2', 'Beta')];

function renderHeader(over: Partial<Parameters<typeof WikiScopeHeader>[0]> = {}) {
  const onScopeChange = vi.fn();
  render(
    <WikiScopeHeader
      agentScopeId={null}
      agents={AGENTS}
      agentsLoading={false}
      onScopeChange={onScopeChange}
      {...over}
    />,
  );
  return { onScopeChange };
}

const select = () => document.querySelector('[data-slot="select"]');

beforeEach(resetKit);
afterEach(cleanup);

describe('WikiScopeHeader', () => {
  it('shows the title, the description and what the scope picker is for', () => {
    renderHeader();
    expect(screen.getByRole('heading', { level: 2 }).textContent).toBe('title');
    expect(screen.getByText('description')).toBeTruthy();
    expect(screen.getByText('agentScopeLabel')).toBeTruthy();
  });

  it('offers the default scope first, then every agent under its localised name', () => {
    world.locale = 'ja';
    renderHeader();
    expect(screen.getAllByRole('option').map((option) => option.textContent)).toEqual([
      'agentScopeDefault',
      'a1:Alpha:ja',
      'a2:Beta:ja',
    ]);
  });

  it.each([
    [null, 'default', 'defaultScopeNotice'],
    ['a2', 'a2', 'agentScopeNotice'],
  ])('with scope %s the picker shows %s and the notice says %s', (scope, value, notice) => {
    renderHeader({ agentScopeId: scope });
    expect(select()?.getAttribute('data-value')).toBe(value);
    expect(screen.getByText(notice)).toBeTruthy();
  });

  it('reports the chosen scope, and "default" for the default option', async () => {
    const { onScopeChange } = renderHeader({ agentScopeId: 'a1' });
    await click(screen.getByRole('option', { name: 'a2:Beta:en' }));
    expect(onScopeChange).toHaveBeenLastCalledWith('a2');
    await click(screen.getByRole('option', { name: 'agentScopeDefault' }));
    expect(onScopeChange).toHaveBeenLastCalledWith('default');
    expect(onScopeChange).toHaveBeenCalledTimes(2);
  });

  it.each([
    [true, '1', 'loading'],
    [false, '0', 'agentScopePlaceholder'],
  ])(
    'with agents loading = %s the picker is disabled = %s and the placeholder says %s',
    (loading, disabled, placeholder) => {
      renderHeader({ agentsLoading: loading });
      expect(select()?.getAttribute('data-disabled')).toBe(disabled);
      expect(document.querySelector('[data-slot="select-value"]')?.textContent).toBe(placeholder);
    },
  );
});
