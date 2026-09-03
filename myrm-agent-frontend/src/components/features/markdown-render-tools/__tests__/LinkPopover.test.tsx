import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('@/lib/utils/deviceUtils', () => ({
  isTouchDevice: () => false,
}));

import LinkPopover, { formatRelativeDate } from '../LinkPopover';

const stableT = (key: string, values?: Record<string, number | string>) => {
  const map: Record<string, string> = {
    clickToVisitLink: 'Click to visit link',
    agentBrowse: 'Agent browse',
    'relativeDate.today': 'Today',
    'relativeDate.yesterday': 'Yesterday',
  };
  if (key === 'relativeDate.daysAgo') {
    return `${values?.count} days ago`;
  }
  if (key === 'agentBrowsePrompt') {
    return `Please open and analyze this link in the browser: ${values?.url}`;
  }
  return map[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('formatRelativeDate', () => {
  it('formats invalid dates by returning raw string', () => {
    expect(formatRelativeDate('invalid-date', stableT)).toBe('invalid-date');
  });

  it('formats today correctly', () => {
    const nowIso = new Date().toISOString();
    expect(formatRelativeDate(nowIso, stableT)).toBe('Today');
  });

  it('formats days ago correctly', () => {
    const twoDaysAgo = new Date(Date.now() - 2 * 86_400_000).toISOString();
    expect(formatRelativeDate(twoDaysAgo, stableT)).toBe('2 days ago');
  });
});

describe('LinkPopover', () => {
  it('renders citation anchor badge when valid url is passed', () => {
    render(
      <LinkPopover
        url="https://example.com/doc"
        title="Example Documentation"
        label="1"
        siteName="Example"
      />,
    );

    const anchor = screen.getByRole('link', { name: '1' });
    expect(anchor).toBeInTheDocument();
    expect(anchor).toHaveAttribute('href', 'https://example.com/doc');
    expect(anchor).toHaveAttribute('target', '_blank');
    expect(anchor).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('renders non-anchor span when url is hash or empty', () => {
    render(
      <LinkPopover
        url="#"
        title="Internal Reference"
        label="2"
      />,
    );

    const badge = screen.getByText('2');
    expect(badge.tagName).toBe('SPAN');
    expect(screen.queryByRole('link')).toBeNull();
  });
});
