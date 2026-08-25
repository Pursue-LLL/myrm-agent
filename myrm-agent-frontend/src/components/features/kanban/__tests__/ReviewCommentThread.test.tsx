/** @vitest-environment jsdom */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ReviewCommentThread } from '../ReviewCommentThread';
import type { AcceptanceResultItem } from '../ReviewCommentThread';

const translations: Record<string, string> = {
  completionCriteria: 'Acceptance Criteria',
  acceptancePassed: 'Passed',
  acceptanceFailed: 'Failed',
  reviewCommentsTitle: 'Review Comments',
  reviewFilterAll: 'All',
  reviewSeverityCritical: 'Critical',
  reviewSeverityWarning: 'Warning',
  reviewSeverityInfo: 'Info',
  reviewFixAction: 'Fix',
  reviewFixSuggestion: 'Fix Suggestion',
  copy: 'Copy',
  copied: 'Copied',
};

const mockT = (key: string) => translations[key] || key;

describe('ReviewCommentThread', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });
  });

  it('renders criteria passed and failed summary cards with duration', () => {
    const results: AcceptanceResultItem[] = [
      {
        label: 'Run pytest suite',
        passed: true,
        duration_ms: 120,
      },
      {
        label: 'Lint check',
        passed: false,
        duration_ms: 45,
        reason: 'Type error found in main.py',
      },
    ];

    render(<ReviewCommentThread results={results} t={mockT} />);

    expect(screen.getByText('Run pytest suite')).toBeDefined();
    expect(screen.getByText('Lint check')).toBeDefined();
    expect(screen.getByText('120ms')).toBeDefined();
    expect(screen.getByText('45ms')).toBeDefined();
    expect(screen.getByText('Passed')).toBeDefined();
    expect(screen.getByText('Failed')).toBeDefined();
  });

  it('renders review comments with critical, warning, and info severity badges and filters', () => {
    const results: AcceptanceResultItem[] = [
      {
        label: 'Security Check',
        passed: false,
        comments: [
          {
            id: 'c1',
            severity: 'critical',
            message: 'SQL injection risk detected in query builder',
            target_path: 'app/db/query.py',
            line_range: '42-50',
            fix_suggestion: 'Use parameterized queries instead of f-strings',
          },
          {
            id: 'c2',
            severity: 'warning',
            message: 'Deprecated helper method used',
            target_path: 'app/utils/helpers.py',
          },
          {
            id: 'c3',
            severity: 'info',
            message: 'Consider adding more docstrings',
          },
        ],
      },
    ];

    render(<ReviewCommentThread results={results} t={mockT} />);

    expect(screen.getByText('Review Comments (3)')).toBeDefined();
    expect(screen.getByText('SQL injection risk detected in query builder')).toBeDefined();
    expect(screen.getByText('Deprecated helper method used')).toBeDefined();
    expect(screen.getByText('Consider adding more docstrings')).toBeDefined();

    // Filter by Critical
    const criticalFilter = screen.getByText('Critical (1)');
    fireEvent.click(criticalFilter);

    expect(screen.getByText('SQL injection risk detected in query builder')).toBeDefined();
    expect(screen.queryByText('Deprecated helper method used')).toBeNull();
    expect(screen.queryByText('Consider adding more docstrings')).toBeNull();

    // Filter by Warning
    const warningFilter = screen.getByText('Warning (1)');
    fireEvent.click(warningFilter);

    expect(screen.queryByText('SQL injection risk detected in query builder')).toBeNull();
    expect(screen.getByText('Deprecated helper method used')).toBeDefined();
    expect(screen.queryByText('Consider adding more docstrings')).toBeNull();

    // Filter by All
    const allFilter = screen.getByText('All (3)');
    fireEvent.click(allFilter);

    expect(screen.getByText('SQL injection risk detected in query builder')).toBeDefined();
    expect(screen.getByText('Deprecated helper method used')).toBeDefined();
    expect(screen.getByText('Consider adding more docstrings')).toBeDefined();
  });

  it('toggles fix suggestion and allows copying suggestion to clipboard', async () => {
    const results: AcceptanceResultItem[] = [
      {
        passed: false,
        comments: [
          {
            id: 'c1',
            severity: 'critical',
            message: 'Missing error boundary',
            fix_suggestion: 'Wrap component with ErrorBoundary',
          },
        ],
      },
    ];

    render(<ReviewCommentThread results={results} t={mockT} />);

    const toggleButton = screen.getByText('Fix Suggestion');
    expect(screen.queryByText('Wrap component with ErrorBoundary')).toBeNull();

    // Expand
    fireEvent.click(toggleButton);
    expect(screen.getByText('Wrap component with ErrorBoundary')).toBeDefined();

    // Copy
    const copyButton = screen.getByRole('button', { name: /copy/i });
    fireEvent.click(copyButton);
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('Wrap component with ErrorBoundary');
  });

  it('triggers onInitiateFix callback when Fix button is clicked on critical comment', () => {
    const onInitiateFix = vi.fn();
    const commentItem = {
      id: 'c1',
      severity: 'critical' as const,
      message: 'Syntax error in config parser',
    };
    const results: AcceptanceResultItem[] = [
      {
        passed: false,
        comments: [commentItem],
      },
    ];

    render(<ReviewCommentThread results={results} t={mockT} onInitiateFix={onInitiateFix} />);

    const fixButton = screen.getByText('Fix');
    fireEvent.click(fixButton);

    expect(onInitiateFix).toHaveBeenCalledTimes(1);
    expect(onInitiateFix).toHaveBeenCalledWith(expect.objectContaining({
      message: 'Syntax error in config parser',
      severity: 'critical',
    }));
  });

  it('creates fallback critical comment when task failed with reason but no comments array', () => {
    const results: AcceptanceResultItem[] = [
      {
        label: 'Compilation Gate',
        passed: false,
        reason: 'Build command returned non-zero exit code 1',
      },
    ];

    render(<ReviewCommentThread results={results} t={mockT} />);

    expect(screen.getByText('Review Comments (1)')).toBeDefined();
    expect(screen.getByText('Build command returned non-zero exit code 1')).toBeDefined();
  });
});
