import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';

const stableT = (key: string) => {
  const map: Record<string, string> = {
    switchToTable: 'Switch to table view',
    switchToCard: 'Switch to card view',
    tableView: 'Table',
    cardView: 'Card',
  };
  return map[key] ?? key;
};

vi.mock('next-intl', async () => {
  const actual = await vi.importActual<typeof import('next-intl')>('next-intl');
  return {
    ...actual,
    useTranslations: () => stableT,
  };
});

import ResponsiveTable from '../ResponsiveTable';

const renderWithProviders = (ui: React.ReactElement) => {
  const messages = {
    MarkdownTable: {
      switchToTable: 'Switch to table view',
      switchToCard: 'Switch to card view',
      tableView: 'Table',
      cardView: 'Card',
    },
  };
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      {ui}
    </NextIntlClientProvider>,
  );
};

const makeTable = (cols: number, rows: number = 2, useColspan = false) => (
  <>
    <thead>
      <tr>
        {Array.from({ length: cols }, (_, i) => (
          <th key={i}>H{i + 1}</th>
        ))}
      </tr>
    </thead>
    <tbody>
      {Array.from({ length: rows }, (_, r) => (
        <tr key={r}>
          {useColspan && r === 0 ? (
            <td colSpan={cols}>merged</td>
          ) : (
            Array.from({ length: cols }, (_, c) => (
              <td key={c}>
                R{r + 1}C{c + 1}
              </td>
            ))
          )}
        </tr>
      ))}
    </tbody>
  </>
);

describe('ResponsiveTable', () => {
  it('renders a basic table with wrapper', () => {
    const { container } = renderWithProviders(
      <ResponsiveTable>{makeTable(3)}</ResponsiveTable>,
    );
    expect(container.querySelector('.responsive-table-wrapper')).toBeTruthy();
    expect(container.querySelector('.responsive-table')).toBeTruthy();
    expect(container.querySelector('.not-prose')).toBeTruthy();
  });

  it('does NOT show toggle for tables with fewer than 4 columns', () => {
    renderWithProviders(
      <ResponsiveTable>{makeTable(3)}</ResponsiveTable>,
    );
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('shows toggle for tables with >= 4 columns', () => {
    renderWithProviders(
      <ResponsiveTable>{makeTable(5)}</ResponsiveTable>,
    );
    const btn = screen.getByRole('button');
    expect(btn).toBeTruthy();
    expect(btn.textContent).toContain('Table');
  });

  it('toggles between card and table view', () => {
    const { container } = renderWithProviders(
      <ResponsiveTable>{makeTable(5)}</ResponsiveTable>,
    );

    expect(container.querySelector('.responsive-table-cards')).toBeTruthy();

    const btn = screen.getByRole('button');
    fireEvent.click(btn);

    expect(container.querySelector('.responsive-table-cards')).toBeNull();
    expect(btn.textContent).toContain('Card');

    fireEvent.click(btn);
    expect(container.querySelector('.responsive-table-cards')).toBeTruthy();
  });

  it('injects data-label attributes in card mode', () => {
    const { container } = renderWithProviders(
      <ResponsiveTable>{makeTable(4)}</ResponsiveTable>,
    );

    const tds = container.querySelectorAll('tbody td');
    expect(tds.length).toBeGreaterThan(0);
    expect(tds[0].getAttribute('data-label')).toBe('H1');
    expect(tds[1].getAttribute('data-label')).toBe('H2');
  });

  it('disables card view when colspan is present', () => {
    renderWithProviders(
      <ResponsiveTable>{makeTable(5, 2, true)}</ResponsiveTable>,
    );
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('disables card view when isStreaming is true', () => {
    renderWithProviders(
      <ResponsiveTable isStreaming>{makeTable(5)}</ResponsiveTable>,
    );
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('handles table with no thead gracefully', () => {
    const { container } = renderWithProviders(
      <ResponsiveTable>
        <tbody>
          <tr>
            <td>A</td>
            <td>B</td>
          </tr>
        </tbody>
      </ResponsiveTable>,
    );
    expect(container.querySelector('.responsive-table')).toBeTruthy();
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('applies not-prose class to prevent Tailwind prose interference', () => {
    const { container } = renderWithProviders(
      <ResponsiveTable>{makeTable(3)}</ResponsiveTable>,
    );
    const wrapper = container.firstElementChild;
    expect(wrapper?.classList.contains('not-prose')).toBe(true);
  });
});
