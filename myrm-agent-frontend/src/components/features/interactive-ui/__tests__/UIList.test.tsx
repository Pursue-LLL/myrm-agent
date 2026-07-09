/** @vitest-environment jsdom */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { UIList } from '../components/UIList';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

const defaultProps = {
  id: 'list-1',
  props: {},
  bindings: { data: '$.items' },
  events: {},
  data: {},
  onDataChange: vi.fn(),
  onAction: vi.fn(),
};

describe('UIList', () => {
  it('renders empty state when data is not an array', () => {
    render(<UIList {...defaultProps} data={{ items: 'not-an-array' }} />);
    expect(screen.getByText('noData')).toBeInTheDocument();
  });

  it('renders list items from bindings.data', () => {
    render(
      <UIList
        {...defaultProps}
        data={{
          items: [
            { id: 'a', title: 'Alpha', subtitle: 'first' },
            { title: 'Beta' },
          ],
        }}
      />,
    );
    expect(screen.getByText('Alpha')).toBeInTheDocument();
    expect(screen.getByText('first')).toBeInTheDocument();
    expect(screen.getByText('Beta')).toBeInTheDocument();
  });

  it('renders children when provided', () => {
    render(
      <UIList {...defaultProps}>
        <li>child item</li>
      </UIList>,
    );
    expect(screen.getByText('child item')).toBeInTheDocument();
  });
});
