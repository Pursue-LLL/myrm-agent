import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { UITable } from '../components/UITable';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

const defaultProps = {
  id: 'tbl-1',
  props: {
    columns: [
      { key: 'name', title: 'Name' },
      { key: 'age', title: 'Age' },
    ],
  },
  bindings: { data: '$.rows' },
  events: {},
  data: {},
  onDataChange: vi.fn(),
  onAction: vi.fn(),
};

describe('UITable', () => {
  describe('Array.isArray defensive check', () => {
    it('renders empty state when data path resolves to string (non-array truthy)', () => {
      const props = {
        ...defaultProps,
        data: { rows: 'not-an-array' },
      };
      render(<UITable {...props} />);
      expect(screen.getByText('noData')).toBeInTheDocument();
    });

    it('renders empty state when data path resolves to object (non-array truthy)', () => {
      const props = {
        ...defaultProps,
        data: { rows: { a: 1, b: 2 } },
      };
      render(<UITable {...props} />);
      expect(screen.getByText('noData')).toBeInTheDocument();
    });

    it('renders empty state when data path resolves to number', () => {
      const props = {
        ...defaultProps,
        data: { rows: 42 },
      };
      render(<UITable {...props} />);
      expect(screen.getByText('noData')).toBeInTheDocument();
    });

    it('renders empty state when data path resolves to boolean true', () => {
      const props = {
        ...defaultProps,
        data: { rows: true },
      };
      render(<UITable {...props} />);
      expect(screen.getByText('noData')).toBeInTheDocument();
    });

    it('renders empty state when data path resolves to null', () => {
      const props = {
        ...defaultProps,
        data: { rows: null },
      };
      render(<UITable {...props} />);
      expect(screen.getByText('noData')).toBeInTheDocument();
    });

    it('renders empty state when data path resolves to undefined', () => {
      render(<UITable {...defaultProps} />);
      expect(screen.getByText('noData')).toBeInTheDocument();
    });

    it('renders rows when data is a valid array', () => {
      const props = {
        ...defaultProps,
        data: {
          rows: [
            { name: 'Alice', age: 30 },
            { name: 'Bob', age: 25 },
          ],
        },
      };
      render(<UITable {...props} />);
      expect(screen.getByText('Alice')).toBeInTheDocument();
      expect(screen.getByText('Bob')).toBeInTheDocument();
      expect(screen.queryByText('noData')).not.toBeInTheDocument();
    });

    it('renders empty state when data is empty array', () => {
      const props = {
        ...defaultProps,
        data: { rows: [] },
      };
      render(<UITable {...props} />);
      expect(screen.getByText('noData')).toBeInTheDocument();
    });
  });

  describe('i18n', () => {
    it('uses translated noData key for empty state', () => {
      render(<UITable {...defaultProps} />);
      expect(screen.getByText('noData')).toBeInTheDocument();
    });
  });

  describe('no bindings', () => {
    it('renders empty state when no data binding is specified', () => {
      const props = {
        ...defaultProps,
        bindings: {},
        data: { rows: [{ name: 'A', age: 1 }] },
      };
      render(<UITable {...props} />);
      expect(screen.getByText('noData')).toBeInTheDocument();
    });
  });

  describe('nested data path', () => {
    it('resolves nested JSONPath like $.form.tableData', () => {
      const props = {
        ...defaultProps,
        bindings: { data: '$.form.tableData' },
        data: {
          form: {
            tableData: [{ name: 'Nested', age: 99 }],
          },
        },
      };
      render(<UITable {...props} />);
      expect(screen.getByText('Nested')).toBeInTheDocument();
      expect(screen.getByText('99')).toBeInTheDocument();
    });

    it('handles missing intermediate path gracefully', () => {
      const props = {
        ...defaultProps,
        bindings: { data: '$.nonexistent.path' },
        data: {},
      };
      render(<UITable {...props} />);
      expect(screen.getByText('noData')).toBeInTheDocument();
    });
  });

  describe('cell rendering edge cases', () => {
    it('renders null/undefined cell values as empty string', () => {
      const props = {
        ...defaultProps,
        data: {
          rows: [{ name: null, age: undefined }],
        },
      };
      render(<UITable {...props} />);
      const cells = document.querySelectorAll('td');
      expect(cells[0].textContent).toBe('');
      expect(cells[1].textContent).toBe('');
    });

    it('renders numeric zero correctly', () => {
      const props = {
        ...defaultProps,
        data: {
          rows: [{ name: 'Zero', age: 0 }],
        },
      };
      render(<UITable {...props} />);
      expect(screen.getByText('0')).toBeInTheDocument();
    });
  });

  describe('column header rendering', () => {
    it('renders column headers even when data is empty', () => {
      render(<UITable {...defaultProps} />);
      expect(screen.getByText('Name')).toBeInTheDocument();
      expect(screen.getByText('Age')).toBeInTheDocument();
    });

    it('renders with empty columns array', () => {
      const props = {
        ...defaultProps,
        props: { columns: [] },
      };
      render(<UITable {...props} />);
      expect(screen.getByText('noData')).toBeInTheDocument();
    });
  });

  describe('selectable rows', () => {
    it('renders checkbox column and updates selected ids binding', () => {
      const onDataChange = vi.fn();
      const props = {
        ...defaultProps,
        props: {
          columns: [{ key: 'name', title: 'Name' }],
          selectable: true,
          rowIdKey: 'id',
        },
        bindings: { data: '$.rows', selected: '$.selected_ids' },
        data: {
          rows: [
            { id: 'row-a', name: 'Alpha' },
            { id: 'row-b', name: 'Beta' },
          ],
          selected_ids: [],
        },
        onDataChange,
      };
      render(<UITable {...props} />);

      const checkboxes = screen.getAllByRole('checkbox');
      expect(checkboxes).toHaveLength(2);
      checkboxes[0].click();
      expect(onDataChange).toHaveBeenCalledWith('$.selected_ids', ['row-a']);
    });

    it('toggles row off when checkbox is clicked twice', () => {
      const onDataChange = vi.fn();
      const props = {
        ...defaultProps,
        props: {
          columns: [{ key: 'name', title: 'Name' }],
          selectable: true,
        },
        bindings: { data: '$.rows', selected: '$.selected_ids' },
        data: {
          rows: [{ id: 'row-a', name: 'Alpha' }],
          selected_ids: ['row-a'],
        },
        onDataChange,
      };
      render(<UITable {...props} />);

      screen.getByRole('checkbox').click();
      expect(onDataChange).toHaveBeenCalledWith('$.selected_ids', []);
    });
  });
});
