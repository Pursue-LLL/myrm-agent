import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { SpreadsheetSelectionToolbar } from '../SpreadsheetSelectionToolbar';
import { useScopedArtifactStore } from '@/store/useScopedArtifactStore';

const stableT = (key: string, values?: Record<string, unknown>) => {
  const map: Record<string, string> = {
    search: 'Search...',
    rows: 'rows',
    of: 'of',
    copy: 'Copy',
    export: 'Export',
    copyAll: 'Copy all to clipboard',
    exportCsv: 'Export as CSV',
    quoteRow: `Quote row ${values?.row ?? ''}`,
    quoteRowTooltip: 'Quote selected row to composer for targeted inquiry or partial edit',
    quote: 'Quote to Composer',
  };
  return map[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('SpreadsheetSelectionToolbar', () => {
  beforeEach(() => {
    useScopedArtifactStore.getState().clearTarget();
  });

  it('renders nothing when no row is selected', () => {
    const { container } = render(
      <SpreadsheetSelectionToolbar
        selectedRowIndex={null}
        headers={['Name', 'Age']}
        rowData={null}
        onClearSelection={vi.fn()}
      />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders toolbar with row label and triggers quote to store', () => {
    const onClear = vi.fn();
    render(
      <SpreadsheetSelectionToolbar
        selectedRowIndex={1}
        headers={['Item', 'Price']}
        rowData={['Apple', '$3']}
        filename="market.xlsx"
        sheetName="Sheet1"
        onClearSelection={onClear}
      />
    );

    expect(screen.getByText('Sheet1!Row 2')).toBeDefined();

    const quoteBtn = screen.getByTitle('Quote to Composer');
    fireEvent.click(quoteBtn);

    const target = useScopedArtifactStore.getState().target;
    expect(target).not.toBeNull();
    expect(target?.artifactName).toBe('market.xlsx');
    expect(target?.kind).toBe('spreadsheet');
    expect(target?.scopeLabel).toBe('Sheet1!Row 2');
    expect(target?.selectedSnippet).toContain('Item: Apple');
  });

  it('calls onClearSelection when clear button is clicked', () => {
    const onClear = vi.fn();
    render(
      <SpreadsheetSelectionToolbar
        selectedRowIndex={0}
        headers={['Col1']}
        rowData={['Val1']}
        onClearSelection={onClear}
      />
    );

    const clearBtn = screen.getByLabelText('Clear selection');
    fireEvent.click(clearBtn);
    expect(onClear).toHaveBeenCalled();
  });
});
