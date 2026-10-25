import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import WaitingTtftIndicator from '../WaitingTtftIndicator';

const translate = (key: string, params?: Record<string, unknown>) =>
  params ? `${key}:${JSON.stringify(params)}` : key;

vi.mock('next-intl', () => ({
  useTranslations: () => translate,
}));

describe('WaitingTtftIndicator', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('keeps a live elapsed counter so a slow first token does not look frozen', () => {
    vi.useFakeTimers();
    render(<WaitingTtftIndicator />);

    expect(screen.getByText('reasoningThinking:{"seconds":0}')).toBeDefined();
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(screen.getByText('reasoningThinking:{"seconds":2}')).toBeDefined();
    expect(screen.getByLabelText('thinking')).toBeDefined();
  });
});
