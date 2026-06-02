'use client';

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import MessageListSkeleton from '../MessageListSkeleton';

describe('MessageListSkeleton', () => {
  it('renders container with aria-label', () => {
    render(<MessageListSkeleton />);
    expect(screen.getByLabelText('Loading messages')).toBeInTheDocument();
  });

  it('renders 4 skeleton bubbles', () => {
    const { container } = render(<MessageListSkeleton />);
    const bubbles = container.querySelectorAll('.rounded-2xl');
    expect(bubbles).toHaveLength(4);
  });

  it('renders right-aligned bubbles with justify-end', () => {
    const { container } = render(<MessageListSkeleton />);
    const rightBubbles = container.querySelectorAll('.justify-end');
    expect(rightBubbles).toHaveLength(2);
  });

  it('renders left-aligned bubbles with justify-start', () => {
    const { container } = render(<MessageListSkeleton />);
    const leftBubbles = container.querySelectorAll('.justify-start');
    expect(leftBubbles).toHaveLength(2);
  });

  it('renders correct number of skeleton lines per bubble', () => {
    const { container } = render(<MessageListSkeleton />);
    const pulseLines = container.querySelectorAll('.animate-pulse');
    // ROWS: [2, 3, 1, 3] = 9 total lines
    expect(pulseLines).toHaveLength(9);
  });

  it('applies staggered animation delays', () => {
    const { container } = render(<MessageListSkeleton />);
    const pulseLines = container.querySelectorAll('.animate-pulse');
    const firstDelay = (pulseLines[0] as HTMLElement).style.animationDelay;
    const secondDelay = (pulseLines[1] as HTMLElement).style.animationDelay;
    expect(firstDelay).toBe('0ms');
    expect(secondDelay).toBe('80ms');
  });

  it('applies responsive max-width classes', () => {
    const { container } = render(<MessageListSkeleton />);
    const rightBubble = container.querySelector('.max-w-\\[65\\%\\]');
    const leftBubble = container.querySelector('.max-w-\\[85\\%\\]');
    expect(rightBubble).toBeInTheDocument();
    expect(leftBubble).toBeInTheDocument();
  });
});
