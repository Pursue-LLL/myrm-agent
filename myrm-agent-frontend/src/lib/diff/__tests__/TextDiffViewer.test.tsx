import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { TextDiffViewer } from '../TextDiffViewer';

vi.mock('next-themes', () => ({
  useTheme: () => ({ theme: 'light', resolvedTheme: 'light' }),
}));

const stableT = (key: string, values?: Record<string, number>) => (values ? `${key} ${JSON.stringify(values)}` : key);

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const numbered = (prefix: string, count: number) =>
  Array.from({ length: count }, (_, index) => `${prefix} ${index + 1}`).join('\n');

describe('TextDiffViewer', () => {
  it('renders added and removed lines from old/new text', () => {
    render(<TextDiffViewer oldValue={'alpha\nbeta'} newValue={'alpha\ngamma'} filePath="demo.txt" />);
    expect(screen.getByText(/beta/)).toBeInTheDocument();
    expect(screen.getByText(/gamma/)).toBeInTheDocument();
  });

  it('does not offer the fallback for a change it can compare', () => {
    render(<TextDiffViewer oldValue={'alpha\nbeta'} newValue={'alpha\ngamma'} filePath="demo.txt" />);

    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('says a rewrite is too large to compare, with both sizes, instead of freezing the page on it', () => {
    const started = performance.now();
    render(<TextDiffViewer oldValue={numbered('old', 6000)} newValue={numbered('new', 6000)} filePath="big.txt" />);
    const elapsed = performance.now() - started;

    const notice = screen.getByRole('status');
    expect(notice).toHaveTextContent('diffTooLarge');
    expect(notice).toHaveTextContent('"oldLines":6000');
    expect(notice).toHaveTextContent('"newLines":6000');
    expect(screen.queryByText('old 1')).not.toBeInTheDocument();
    // Comparing this pair takes several seconds without a budget; the budget is half a second.
    expect(elapsed).toBeLessThan(3000);
  });

  it('counts lines the way a person does: a final line break is not another line', () => {
    render(
      <TextDiffViewer
        oldValue={`${numbered('old', 6000)}\n`}
        newValue={`${numbered('new', 6000)}\n`}
        filePath="big.txt"
      />,
    );

    expect(screen.getByRole('status')).toHaveTextContent('"oldLines":6000');
  });
});
