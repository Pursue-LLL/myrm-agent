import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { RedactionFindings } from '../useRedactionDecisions';
import RedactionReview from '../RedactionReview';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, values?: Record<string, string | number>) =>
    values ? `${key} ${Object.values(values).join(',')}` : key,
}));

vi.mock('@/components/primitives/scroll-area', () => ({
  ScrollArea: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const FINDINGS: RedactionFindings = {
  'SKILL.md': [
    { line_number: 3, original: 'api_key=sk-1', redacted: 'api_key=<REDACTED>', reason: 'API key' },
    { line_number: 9, original: 'password=abc', redacted: 'password=<REDACTED>', reason: 'Password' },
  ],
  'agents/lead.md': [{ line_number: 1, original: 'token=t-1', redacted: 'token=<REDACTED>', reason: 'Token' }],
};

function renderReview(ignored: Record<string, number[]> = {}, disabled = false) {
  const onToggle = vi.fn();
  const onToggleAll = vi.fn();
  render(
    <RedactionReview
      findings={FINDINGS}
      ignored={ignored}
      onToggle={onToggle}
      onToggleAll={onToggleAll}
      disabled={disabled}
    />,
  );
  return { onToggle, onToggleAll };
}

describe('RedactionReview', () => {
  it('shows every file with the original line and its replacement', () => {
    renderReview();

    expect(screen.getByText('SKILL.md')).toBeInTheDocument();
    expect(screen.getByText('agents/lead.md')).toBeInTheDocument();
    expect(screen.getByText('api_key=sk-1')).toBeInTheDocument();
    expect(screen.getByText('api_key=<REDACTED>')).toBeInTheDocument();
    expect(screen.getByText('line 3')).toBeInTheDocument();
    expect(screen.getByText('Password')).toBeInTheDocument();
  });

  it('shows a kept finding without a replacement line', () => {
    renderReview({ 'SKILL.md': [1] });

    expect(screen.getByText('password=abc')).toBeInTheDocument();
    expect(screen.queryByText('password=<REDACTED>')).not.toBeInTheDocument();
    // The other finding of the same file is still redacted.
    expect(screen.getByText('api_key=<REDACTED>')).toBeInTheDocument();
  });

  it('reports which finding or file the author toggled', () => {
    const { onToggle, onToggleAll } = renderReview();
    const boxes = screen.getAllByRole('checkbox');

    // Order: [file SKILL.md, finding 0, finding 1, file agents/lead.md, finding 0]
    fireEvent.click(boxes[2]);
    expect(onToggle).toHaveBeenCalledWith('SKILL.md', 1);

    fireEvent.click(boxes[3]);
    expect(onToggleAll).toHaveBeenCalledWith('agents/lead.md', 1);
  });

  it('marks a finding as redacted unless it is kept', () => {
    renderReview({ 'SKILL.md': [0] });
    const boxes = screen.getAllByRole('checkbox');

    expect(boxes[1]).toHaveAttribute('aria-checked', 'false');
    expect(boxes[2]).toHaveAttribute('aria-checked', 'true');
    // The file-level box is checked only while nothing in the file is kept.
    expect(boxes[0]).toHaveAttribute('aria-checked', 'false');
    expect(boxes[3]).toHaveAttribute('aria-checked', 'true');
  });

  it('locks every decision while an export is running', () => {
    renderReview({}, true);

    for (const box of screen.getAllByRole('checkbox')) {
      expect(box).toBeDisabled();
    }
  });
});
