import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => {
    const map: Record<string, string> = {
      search: 'Search...',
      rows: 'rows',
      of: 'of',
      copy: 'Copy',
      export: 'Export',
      copyAll: 'Copy all to clipboard',
      exportCsv: 'Export as CSV',
    };
    return map[key] ?? key;
  },
}));

vi.mock('@tanstack/react-virtual', () => ({
  useVirtualizer: ({ count }: { count: number }) => ({
    getVirtualItems: () =>
      Array.from({ length: Math.min(count, 50) }, (_, i) => ({
        index: i,
        start: i * 32,
        size: 32,
        key: `row-${i}`,
      })),
    getTotalSize: () => count * 32,
    measureElement: vi.fn(),
  }),
}));

import DataGrid from '../DataGrid';

const HEADERS = ['Name', 'Age', 'City'];
const ROWS = [
  ['Alice', '30', 'NYC'],
  ['Bob', '25', 'LA'],
  ['Carol', '35', 'SF'],
];

describe('DataGrid', () => {
  it('renders column headers', () => {
    render(<DataGrid headers={HEADERS} rows={ROWS} />);
    expect(screen.getByText('Name')).toBeDefined();
    expect(screen.getByText('Age')).toBeDefined();
    expect(screen.getByText('City')).toBeDefined();
  });

  it('renders all data cells', () => {
    render(<DataGrid headers={HEADERS} rows={ROWS} />);
    expect(screen.getByText('Alice')).toBeDefined();
    expect(screen.getByText('Bob')).toBeDefined();
    expect(screen.getByText('Carol')).toBeDefined();
    expect(screen.getByText('NYC')).toBeDefined();
    expect(screen.getByText('SF')).toBeDefined();
  });

  it('shows toolbar with controls', () => {
    render(<DataGrid headers={HEADERS} rows={ROWS} />);
    expect(screen.getByText('Copy')).toBeDefined();
    expect(screen.getByText('Export')).toBeDefined();
    expect(screen.getByText(/rows/)).toBeDefined();
  });

  it('has a search input', () => {
    render(<DataGrid headers={HEADERS} rows={ROWS} />);
    const input = screen.getByPlaceholderText('Search...');
    expect(input).toBeDefined();
  });

  it('renders with empty rows', () => {
    render(<DataGrid headers={HEADERS} rows={[]} />);
    expect(screen.getByText('Name')).toBeDefined();
  });

  it('renders with single row', () => {
    render(<DataGrid headers={['Col1']} rows={[['Val1']]} />);
    expect(screen.getByText('Col1')).toBeDefined();
    expect(screen.getByText('Val1')).toBeDefined();
  });

  it('renders numeric cells correctly', () => {
    render(<DataGrid headers={['Price', 'Name']} rows={[['99.99', 'Widget']]} />);
    expect(screen.getByText('99.99')).toBeDefined();
    expect(screen.getByText('Widget')).toBeDefined();
  });

  it('renders many columns', () => {
    const headers = Array.from({ length: 20 }, (_, i) => `Col${i}`);
    const rows = [Array.from({ length: 20 }, (_, i) => `V${i}`)];
    render(<DataGrid headers={headers} rows={rows} />);
    expect(screen.getByText('Col0')).toBeDefined();
    expect(screen.getByText('Col19')).toBeDefined();
  });

  it('renders with unicode content', () => {
    render(<DataGrid headers={['\u540d\u524d', '\u90fd\u5e02']} rows={[['\u592a\u90ce', '\u6771\u4eac']]} />);
    expect(screen.getByText('\u540d\u524d')).toBeDefined();
    expect(screen.getByText('\u592a\u90ce')).toBeDefined();
    expect(screen.getByText('\u6771\u4eac')).toBeDefined();
  });

  it('renders cells with special characters', () => {
    render(
      <DataGrid
        headers={['Data']}
        rows={[['<script>alert("xss")</script>'], ['&amp; entities']]}
      />,
    );
    expect(screen.getByText('<script>alert("xss")</script>')).toBeDefined();
  });

  it('shows totalRows truncation info when provided', () => {
    render(<DataGrid headers={['A']} rows={[['1']]} totalRows={50000} />);
    expect(screen.getByText(/50,000/)).toBeDefined();
  });
});
