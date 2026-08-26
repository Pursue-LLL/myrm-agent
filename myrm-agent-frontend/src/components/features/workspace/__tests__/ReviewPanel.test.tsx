/** @vitest-environment jsdom */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ReviewPanel from '../ReviewPanel';

const stableT = (key: string, params?: Record<string, unknown>) => {
  const translations: Record<string, string> = {
    selectSessionToReview: 'Select an active session to review changes',
    tabDiff: 'Diff ({count})',
    tabMessages: 'Messages',
    noChangesDetected: 'No file changes detected',
    binaryFileDiff: 'Binary file — cannot display diff',
    copyDiff: 'Copy diff',
    copied: 'Copied',
    expandLongDiff: 'Show {count} more lines',
    collapseLongDiff: 'Collapse long diff',
    feedbackPlaceholder: 'Send feedback to this agent...',
    loadingMessages: 'Loading messages...',
    noMessages: 'No messages yet',
  };
  let text = translations[key] || key;
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      text = text.replace(`{${k}}`, String(v));
    });
  }
  return text;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/lib/utils/apiConfig', () => ({
  getBackendUrl: () => 'http://localhost:8080',
}));

vi.mock('@/lib/utils/authHeaders', () => ({
  getAuthHeaders: () => ({ Authorization: 'Bearer test' }),
}));

vi.mock('@/services/chat', () => ({
  getMessages: vi.fn().mockResolvedValue({ messages: [] }),
}));

describe('ReviewPanel Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Mock navigator.clipboard
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockImplementation(() => Promise.resolve()),
      },
    });
  });

  it('renders prompt to select session when sessionId is null', () => {
    render(<ReviewPanel sessionId={null} />);
    expect(screen.getByText('Select an active session to review changes')).toBeInTheDocument();
  });

  it('renders workspacePath badge when workspacePath prop is provided', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    } as Response);

    render(<ReviewPanel sessionId="session-123" workspacePath="/Users/dev/my-project" />);

    await waitFor(() => {
      expect(screen.getByText('/Users/dev/my-project')).toBeInTheDocument();
    });
  });

  it('renders diffs list, expands diff, copies content, and supports long diff fold/expand', async () => {
    // Generate a file with > 300 diff lines
    const originalLines = Array.from({ length: 350 }, (_, i) => `line_${i + 1}_original`).join('\n');
    const currentLines = Array.from({ length: 350 }, (_, i) => `line_${i + 1}_modified`).join('\n');

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        msg1: [
          {
            path: 'src/longFile.ts',
            operation: 'modify',
            original: originalLines,
            current: currentLines,
            isBinary: false,
          },
        ],
      }),
    } as Response);

    render(<ReviewPanel sessionId="session-123" workspacePath="~/code/app" />);

    // Wait for diff item to load
    await waitFor(() => {
      expect(screen.getByText('longFile.ts')).toBeInTheDocument();
    });

    // Toggle file expansion
    fireEvent.click(screen.getByText('longFile.ts'));

    // Verify copy button is present and functional
    const copyButton = screen.getByTitle('Copy diff');
    expect(copyButton).toBeInTheDocument();
    fireEvent.click(copyButton);
    expect(navigator.clipboard.writeText).toHaveBeenCalled();

    // Verify long diff fold button (showing count)
    const expandButton = screen.getByText(/Show \d+ more lines/);
    expect(expandButton).toBeInTheDocument();

    // Click expand
    fireEvent.click(expandButton);
    expect(screen.getByText('Collapse long diff')).toBeInTheDocument();

    // Click collapse
    fireEvent.click(screen.getByText('Collapse long diff'));
    expect(screen.getByText(/Show \d+ more lines/)).toBeInTheDocument();
  });
});
