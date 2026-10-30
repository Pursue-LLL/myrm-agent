/** @vitest-environment jsdom */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { NextIntlClientProvider, type AbstractIntlMessages } from 'next-intl';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { EvolutionStrategyConfig } from '../EvolutionStrategyConfig';

// The global setup stubs next-intl with an identity translator; this suite asserts the real locale copy.
vi.mock('next-intl', async (importOriginal) => importOriginal<typeof import('next-intl')>());

const storeState = vi.hoisted(() => ({ evolutionStrategy: 'balanced', updateEvolutionStrategy: vi.fn() }));
vi.mock('@/store/skill', () => ({ useSkillStore: () => storeState }));

const LOCALES = ['en', 'zh', 'zh-TW', 'ja', 'ko', 'de'] as const;
type Locale = (typeof LOCALES)[number];

function copyFor(locale: Locale): Record<string, string> {
  const file = resolve(__dirname, `../../../../../locales/${locale}.json`);
  return JSON.parse(readFileSync(file, 'utf8')).skills.evolution_strategy;
}

function renderIn(locale: Locale, evolutionStrategy: string) {
  storeState.evolutionStrategy = evolutionStrategy;
  const messages: AbstractIntlMessages = { skills: { evolution_strategy: copyFor(locale) } };
  return render(
    <NextIntlClientProvider locale={locale} messages={messages}>
      <EvolutionStrategyConfig />
    </NextIntlClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  storeState.updateEvolutionStrategy.mockClear();
});

describe('EvolutionStrategyConfig', () => {
  describe.each(LOCALES)('%s', (locale) => {
    it.each(['balanced', 'innovate'] as const)('shows the short %s label and its hint', (strategy) => {
      const copy = copyFor(locale);
      renderIn(locale, strategy);

      const trigger = screen.getByRole('combobox', { name: copy.title });
      expect(trigger).toHaveTextContent(copy[strategy]);
      expect(screen.getByText(copy[`${strategy}_hint`])).toBeInTheDocument();
      expect(trigger.getAttribute('aria-describedby')).toBe(screen.getByText(copy[`${strategy}_hint`]).id);
    });
  });

  it('presents a stored value the server does not know as balanced', () => {
    const copy = copyFor('en');
    renderIn('en', 'conservative');

    expect(screen.getByRole('combobox')).toHaveTextContent(copy.balanced);
    expect(screen.getByText(copy.balanced_hint)).toBeInTheDocument();
  });

  it('saves the strategy picked from the list', () => {
    const copy = copyFor('en');
    renderIn('en', 'balanced');

    fireEvent.keyDown(screen.getByRole('combobox'), { key: 'Enter' });
    const listbox = screen.getByRole('listbox');
    expect(within(listbox).getAllByRole('option').map((option) => option.textContent)).toEqual([copy.balanced, copy.innovate]);
    fireEvent.click(within(listbox).getByRole('option', { name: copy.innovate }));

    expect(storeState.updateEvolutionStrategy).toHaveBeenCalledWith('innovate');
  });
});
