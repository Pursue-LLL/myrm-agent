import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';

const stableT = (key: string): string => {
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

const makeTable = (cols: number, rows: number = 2, useColspan = false): React.ReactElement => (
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
  beforeEach(() => {
    HTMLDialogElement.prototype.showModal = function mockShowModal() {
      this.open = true;
    };
    HTMLDialogElement.prototype.close = function mockClose() {
      this.open = false;
    };
  });

  afterEach(() => {
    delete (HTMLDialogElement.prototype as Partial<HTMLDialogElement>).showModal;
    delete (HTMLDialogElement.prototype as Partial<HTMLDialogElement>).close;
  });

  it('renders a basic table with wrapper and host DOM structure', () => {
    const { container } = renderWithProviders(<ResponsiveTable>{makeTable(3)}</ResponsiveTable>);
    expect(container.querySelector('.responsive-table-wrapper')).toBeTruthy();
    expect(container.querySelector('.responsive-table')).toBeTruthy();
    expect(container.querySelector('.not-prose')).toBeTruthy();
  });

  it('does NOT show toolbar for tables with fewer than 4 columns', () => {
    renderWithProviders(<ResponsiveTable>{makeTable(3)}</ResponsiveTable>);
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('shows toolbar for tables with >= 4 columns with standard SVG icons and zero emoji', () => {
    const { container } = renderWithProviders(<ResponsiveTable>{makeTable(5)}</ResponsiveTable>);
    const buttons = screen.getAllByRole('button');
    expect(buttons.length).toBeGreaterThanOrEqual(2);

    const toggleBtn = buttons[0];
    expect(toggleBtn).toBeTruthy();
    expect(toggleBtn.textContent).toContain('Table');

    // Verify SVG icon exists and no legacy native unicode block emojis exist
    expect(toggleBtn.querySelector('svg')).toBeTruthy();
    expect(container.textContent).not.toContain('▦');
    expect(container.textContent).not.toContain('▤');
  });

  it('toggles between card and table view correctly', () => {
    const { container } = renderWithProviders(<ResponsiveTable>{makeTable(5)}</ResponsiveTable>);

    expect(container.querySelector('.responsive-table-cards')).toBeTruthy();

    const buttons = screen.getAllByRole('button');
    const toggleBtn = buttons[0];
    fireEvent.click(toggleBtn);

    expect(container.querySelector('.responsive-table-cards')).toBeNull();
    expect(toggleBtn.textContent).toContain('Card');

    fireEvent.click(toggleBtn);
    expect(container.querySelector('.responsive-table-cards')).toBeTruthy();
  });

  it('injects data-label attributes in card mode', () => {
    const { container } = renderWithProviders(<ResponsiveTable>{makeTable(4)}</ResponsiveTable>);

    const tds = container.querySelectorAll('tbody td');
    expect(tds.length).toBeGreaterThan(0);
    expect(tds[0]?.getAttribute('data-label')).toBe('H1');
    expect(tds[1]?.getAttribute('data-label')).toBe('H2');
  });

  it('disables card view when colspan is present', () => {
    renderWithProviders(<ResponsiveTable>{makeTable(5, 2, true)}</ResponsiveTable>);
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('disables card view when isStreaming is true and sets data-streaming attribute', () => {
    const { container } = renderWithProviders(<ResponsiveTable isStreaming>{makeTable(5)}</ResponsiveTable>);
    expect(screen.queryByRole('button')).toBeNull();
    const wrapper = container.querySelector('.responsive-table-wrapper');
    expect(wrapper?.getAttribute('data-streaming')).toBe('true');
  });

  it('opens and closes wide table lightbox dialog', () => {
    renderWithProviders(<ResponsiveTable>{makeTable(6)}</ResponsiveTable>);

    // Lightbox closed initially
    expect(screen.queryByRole('dialog')).toBeNull();

    // Click expand button
    const expandBtn = screen.getByRole('button', { name: '展开全景表格' });
    fireEvent.click(expandBtn);

    // Dialog visible
    const dialog = screen.getByRole('dialog');
    expect(dialog).toBeTruthy();
    expect(screen.getByText('全景表格视图')).toBeTruthy();
    expect(screen.getByText('6 列')).toBeTruthy();

    // Close via close button
    const closeBtn = screen.getByRole('button', { name: '关闭预览' });
    fireEvent.click(closeBtn);

    expect(screen.queryByRole('dialog')).toBeNull();
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
    const { container } = renderWithProviders(<ResponsiveTable>{makeTable(3)}</ResponsiveTable>);
    const wrapper = container.firstElementChild;
    expect(wrapper?.classList.contains('not-prose')).toBe(true);
  });
});
