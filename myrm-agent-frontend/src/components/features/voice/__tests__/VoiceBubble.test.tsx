/**
 * Unit tests for VoiceBubble minimized voice surface.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';

const stableT = (key: string) => key;
vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('lucide-react', () => ({
  ChevronUp: () => <span data-testid="chevron-up" />,
}));

import VoiceBubble from '../VoiceBubble';

describe('VoiceBubble', () => {
  it('renders nothing when hidden', () => {
    const { container } = render(
      <VoiceBubble visible={false} sessionState="listening" statusText="" speaking={false} onExpand={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('shows status text and expands on click', () => {
    const onExpand = vi.fn();
    render(
      <VoiceBubble visible sessionState="processing" statusText="reading files" speaking={false} onExpand={onExpand} />,
    );
    expect(screen.getByText('reading files')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button'));
    expect(onExpand).toHaveBeenCalledTimes(1);
  });
});
