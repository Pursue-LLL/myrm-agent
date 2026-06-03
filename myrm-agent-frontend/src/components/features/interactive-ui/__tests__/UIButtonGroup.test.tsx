import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { UIButtonGroup } from '../components/UIButtonGroup';

const baseProps = {
  id: 'bg-1',
  props: {
    options: [
      { value: 'a', label: 'Option A' },
      { value: 'b', label: 'Option B' },
      { value: 'c', label: 'Option C' },
    ],
  },
  bindings: { value: '$.selection' },
  events: {},
  data: {},
  onDataChange: vi.fn(),
  onAction: vi.fn(),
};

describe('UIButtonGroup', () => {
  describe('Array.isArray defensive check (multiple mode)', () => {
    it('treats string value as empty selection in multiple mode', () => {
      const props = {
        ...baseProps,
        props: { ...baseProps.props, multiple: true },
        data: { selection: 'not-an-array' },
      };
      render(<UIButtonGroup {...props} />);

      const buttons = screen.getAllByRole('button');
      buttons.forEach((btn) => {
        expect(btn.className).not.toContain('bg-blue-600');
      });
    });

    it('treats object value as empty selection in multiple mode', () => {
      const props = {
        ...baseProps,
        props: { ...baseProps.props, multiple: true },
        data: { selection: { a: true } },
      };
      render(<UIButtonGroup {...props} />);

      const buttons = screen.getAllByRole('button');
      buttons.forEach((btn) => {
        expect(btn.className).not.toContain('bg-blue-600');
      });
    });

    it('treats number value as empty selection in multiple mode', () => {
      const props = {
        ...baseProps,
        props: { ...baseProps.props, multiple: true },
        data: { selection: 123 },
      };
      render(<UIButtonGroup {...props} />);

      const buttons = screen.getAllByRole('button');
      buttons.forEach((btn) => {
        expect(btn.className).not.toContain('bg-blue-600');
      });
    });

    it('treats null as empty selection in multiple mode', () => {
      const props = {
        ...baseProps,
        props: { ...baseProps.props, multiple: true },
        data: { selection: null },
      };
      render(<UIButtonGroup {...props} />);

      const buttons = screen.getAllByRole('button');
      buttons.forEach((btn) => {
        expect(btn.className).not.toContain('bg-blue-600');
      });
    });

    it('correctly handles valid array value in multiple mode', () => {
      const props = {
        ...baseProps,
        props: { ...baseProps.props, multiple: true },
        data: { selection: ['a', 'c'] },
      };
      render(<UIButtonGroup {...props} />);

      const btnA = screen.getByText('Option A');
      const btnB = screen.getByText('Option B');
      const btnC = screen.getByText('Option C');

      expect(btnA.className).toContain('bg-blue-600');
      expect(btnB.className).not.toContain('bg-blue-600');
      expect(btnC.className).toContain('bg-blue-600');
    });
  });

  describe('single select mode', () => {
    it('selects single value correctly', () => {
      const props = {
        ...baseProps,
        data: { selection: 'b' },
      };
      render(<UIButtonGroup {...props} />);

      const btnB = screen.getByText('Option B');
      expect(btnB.className).toContain('bg-blue-600');

      const btnA = screen.getByText('Option A');
      expect(btnA.className).not.toContain('bg-blue-600');
    });

    it('handles null value in single mode (no selection)', () => {
      const props = {
        ...baseProps,
        data: { selection: null },
      };
      render(<UIButtonGroup {...props} />);

      const buttons = screen.getAllByRole('button');
      buttons.forEach((btn) => {
        expect(btn.className).not.toContain('bg-blue-600');
      });
    });
  });

  describe('interaction', () => {
    it('calls onDataChange with value on click in single mode', () => {
      const onDataChange = vi.fn();
      const props = {
        ...baseProps,
        onDataChange,
      };
      render(<UIButtonGroup {...props} />);

      fireEvent.click(screen.getByText('Option A'));
      expect(onDataChange).toHaveBeenCalledWith('$.selection', 'a');
    });

    it('calls onDataChange with array on click in multiple mode', () => {
      const onDataChange = vi.fn();
      const props = {
        ...baseProps,
        props: { ...baseProps.props, multiple: true },
        data: { selection: ['a'] },
        onDataChange,
      };
      render(<UIButtonGroup {...props} />);

      fireEvent.click(screen.getByText('Option B'));
      expect(onDataChange).toHaveBeenCalledWith('$.selection', ['a', 'b']);
    });

    it('removes value from array on click in multiple mode (deselect)', () => {
      const onDataChange = vi.fn();
      const props = {
        ...baseProps,
        props: { ...baseProps.props, multiple: true },
        data: { selection: ['a', 'b'] },
        onDataChange,
      };
      render(<UIButtonGroup {...props} />);

      fireEvent.click(screen.getByText('Option A'));
      expect(onDataChange).toHaveBeenCalledWith('$.selection', ['b']);
    });

    it('does not call onDataChange when disabled', () => {
      const onDataChange = vi.fn();
      const props = {
        ...baseProps,
        props: { ...baseProps.props, disabled: true },
        onDataChange,
      };
      render(<UIButtonGroup {...props} />);

      fireEvent.click(screen.getByText('Option A'));
      expect(onDataChange).not.toHaveBeenCalled();
    });
  });

  describe('string options normalization', () => {
    it('handles string array options', () => {
      const props = {
        ...baseProps,
        props: { options: ['x', 'y', 'z'] },
      };
      render(<UIButtonGroup {...props} />);
      expect(screen.getByText('x')).toBeInTheDocument();
      expect(screen.getByText('y')).toBeInTheDocument();
      expect(screen.getByText('z')).toBeInTheDocument();
    });
  });

  describe('edge cases', () => {
    it('renders empty when options array is empty', () => {
      const props = {
        ...baseProps,
        props: { options: [] },
      };
      const { container } = render(<UIButtonGroup {...props} />);
      expect(container.querySelectorAll('button')).toHaveLength(0);
    });

    it('does not call onDataChange when no valuePath', () => {
      const onDataChange = vi.fn();
      const props = {
        ...baseProps,
        bindings: {},
        onDataChange,
      };
      render(<UIButtonGroup {...props} />);
      fireEvent.click(screen.getByText('Option A'));
      expect(onDataChange).not.toHaveBeenCalled();
    });

    it('starts from empty selection when multiple mode with non-array then clicks', () => {
      const onDataChange = vi.fn();
      const props = {
        ...baseProps,
        props: { ...baseProps.props, multiple: true },
        data: { selection: 'corrupted-string' },
        onDataChange,
      };
      render(<UIButtonGroup {...props} />);
      fireEvent.click(screen.getByText('Option A'));
      expect(onDataChange).toHaveBeenCalledWith('$.selection', ['a']);
    });

    it('handles nested data path for value binding', () => {
      const props = {
        ...baseProps,
        bindings: { value: '$.form.choice' },
        data: { form: { choice: 'b' } },
      };
      render(<UIButtonGroup {...props} />);
      const btnB = screen.getByText('Option B');
      expect(btnB.className).toContain('bg-blue-600');
    });

    it('renders label when provided', () => {
      const props = {
        ...baseProps,
        props: { ...baseProps.props, label: 'Choose one' },
      };
      render(<UIButtonGroup {...props} />);
      expect(screen.getByText('Choose one')).toBeInTheDocument();
    });

    it('does not render label when not provided', () => {
      render(<UIButtonGroup {...baseProps} />);
      const labels = document.querySelectorAll('label');
      expect(labels).toHaveLength(0);
    });
  });
});
