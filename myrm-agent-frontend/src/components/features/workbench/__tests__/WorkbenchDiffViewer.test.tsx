/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { WorkbenchDiffViewer } from '../tabs/WorkbenchDiffViewer';
import { useWorkbenchStore } from '@/store/useWorkbenchStore';
import type { FileDiffResponse } from '@/services/workbench';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

const mockCustomDiff: FileDiffResponse = {
  file_path: 'app/main.py',
  unified_diff: '--- a/app/main.py\n+++ b/app/main.py\n@@ -1,3 +1,3 @@\n-old line\n+new line',
  additions: 1,
  deletions: 1,
  hunks: [
    {
      old_start: 1,
      old_lines: 1,
      new_start: 1,
      new_lines: 1,
      lines: ['-old line', '+new line'],
    },
  ],
};

describe('WorkbenchDiffViewer component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useWorkbenchStore.setState({
      activeDiff: null,
    });
    // Mock navigator.clipboard
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });
  });

  it('renders default demo diff when activeDiff is null', () => {
    render(<WorkbenchDiffViewer />);

    expect(screen.getByText('src/components/features/agent/runtime.ts')).toBeDefined();
    expect(screen.getAllByText('2').length).toBeGreaterThan(0);
    expect(screen.getAllByText('1').length).toBeGreaterThan(0);
    expect(screen.getByText(/private isIsolated: boolean = true;/)).toBeDefined();
  });

  it('renders custom diff from store when activeDiff is set', () => {
    useWorkbenchStore.setState({ activeDiff: mockCustomDiff });
    render(<WorkbenchDiffViewer />);

    expect(screen.getByText('app/main.py')).toBeDefined();
    expect(screen.getByText('+new line')).toBeDefined();
    expect(screen.getByText('-old line')).toBeDefined();
  });

  it('toggles between inline and split mode', () => {
    render(<WorkbenchDiffViewer />);

    const splitBtn = screen.getByTitle('modeSplit');
    fireEvent.click(splitBtn);

    expect(screen.getByText('originalHeader')).toBeDefined();
    expect(screen.getByText('modifiedHeader')).toBeDefined();

    const inlineBtn = screen.getByTitle('modeInline');
    fireEvent.click(inlineBtn);

    expect(screen.queryByText('originalHeader')).toBeNull();
  });

  it('copies unified diff to clipboard on button click', () => {
    render(<WorkbenchDiffViewer />);

    const copyBtn = screen.getByRole('button', { name: /copyDiff/i });
    fireEvent.click(copyBtn);

    expect(navigator.clipboard.writeText).toHaveBeenCalled();
    expect(screen.getByText('copied')).toBeDefined();
  });

  it('clears active diff when reset button is clicked', () => {
    useWorkbenchStore.setState({ activeDiff: mockCustomDiff });
    render(<WorkbenchDiffViewer />);

    const resetBtn = screen.getByTitle('resetDiff');
    fireEvent.click(resetBtn);

    expect(useWorkbenchStore.getState().activeDiff).toBeNull();
  });
});
