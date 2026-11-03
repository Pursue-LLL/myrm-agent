/** @vitest-environment jsdom */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import InputHistoryPopup from '../InputHistoryPopup';

describe('InputHistoryPopup accessible name', () => {
  it('labels the listbox from translations', () => {
    render(
      <InputHistoryPopup
        popup={{ open: true, entries: [{ text: 'first prompt', createdAt: Date.now() }], activeIndex: 0 }}
        onSelect={vi.fn()}
        onHover={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByRole('listbox', { name: 'inputHistoryLabel' })).toBeInTheDocument();
    expect(screen.getByText('first prompt')).toBeInTheDocument();
  });
});
