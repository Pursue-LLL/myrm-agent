import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ReviewCommentThread, type AcceptanceResultItem } from '../ReviewCommentThread';

const mockT = (key: string) => {
  const translations: Record<string, string> = {
    reviewCommentsTitle: 'Review Comments',
    reviewFilterAll: 'All',
    reviewSeverityCritical: 'Critical',
    reviewSeverityWarning: 'Warning',
    reviewSeverityInfo: 'Info',
    reviewFixAction: 'Copy Fix',
    reviewFixSuggestion: 'Fix Suggestion',
    reviewAdviceSnippet: 'Fix advice',
  };
  return translations[key] || key;
};

describe('ReviewCommentThread', () => {
  it('renders nothing in comment box when results list has no comments', () => {
    const { container } = render(<ReviewCommentThread results={[]} t={mockT} />);
    expect(container.querySelector('[data-testid="review-comment-box"]')).toBeNull();
  });

  it('renders structured review comments with severity badges and allows filtering', () => {
    const sampleResults: AcceptanceResultItem[] = [
      {
        label: 'Unit Test Gate',
        passed: false,
        reason: '2 tests failed',
        comments: [
          {
            id: 'c1',
            severity: 'critical',
            message: 'AssertionError in test_stream',
            target_path: 'app/stream.py',
            line_range: '42-45',
            fix_suggestion: 'Check None before unpacking',
          },
          {
            id: 'c2',
            severity: 'warning',
            message: 'Deprecated method called',
            target_path: 'app/stream.py',
          },
        ],
      },
      {
        label: 'Style Check',
        passed: true,
        comments: [
          {
            id: 'c3',
            severity: 'info',
            message: 'Consider using list comprehension',
          },
        ],
      },
    ];

    render(<ReviewCommentThread results={sampleResults} t={mockT} />);

    // Header title with count
    expect(screen.getByText(/Review Comments/)).toBeInTheDocument();

    // Severity filter buttons
    const filterButtons = screen.getAllByRole('button');
    const allBtn = filterButtons.find(b => b.textContent?.includes('All'));
    const critBtn = filterButtons.find(b => b.textContent?.includes('Critical'));
    const warnBtn = filterButtons.find(b => b.textContent?.includes('Warning'));
    const infoBtn = filterButtons.find(b => b.textContent?.includes('Info'));

    expect(allBtn).toBeDefined();
    expect(critBtn).toBeDefined();
    expect(warnBtn).toBeDefined();
    expect(infoBtn).toBeDefined();

    // Verify critical comment content
    expect(screen.getByText('AssertionError in test_stream')).toBeInTheDocument();
    expect(screen.getByText('app/stream.py:42-45')).toBeInTheDocument();

    // Expand fix suggestion
    fireEvent.click(screen.getByText('Fix Suggestion'));
    expect(screen.getByText('Check None before unpacking')).toBeInTheDocument();

    // Filter to Warning only
    if (warnBtn) fireEvent.click(warnBtn);
    expect(screen.getByText('Deprecated method called')).toBeInTheDocument();
    expect(screen.queryByText('AssertionError in test_stream')).not.toBeInTheDocument();

    // Filter to Critical only
    if (critBtn) fireEvent.click(critBtn);
    expect(screen.getByText('AssertionError in test_stream')).toBeInTheDocument();
    expect(screen.queryByText('Deprecated method called')).not.toBeInTheDocument();
  });

  it('handles fallback comments for failed criteria without structured comments', () => {
    const fallbackResults: AcceptanceResultItem[] = [
      {
        label: 'Shell check',
        passed: false,
        reason: 'exit code 127: command not found',
      },
    ];

    render(<ReviewCommentThread results={fallbackResults} t={mockT} />);

    expect(screen.getByText('Critical (1)')).toBeInTheDocument();
    expect(screen.getByText('exit code 127: command not found')).toBeInTheDocument();
  });
});
