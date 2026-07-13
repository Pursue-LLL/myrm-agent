import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { TextDiffViewer } from '../TextDiffViewer';

vi.mock('next-themes', () => ({
  useTheme: () => ({ theme: 'light' }),
}));

describe('TextDiffViewer', () => {
  it('renders added and removed lines from old/new text', () => {
    render(<TextDiffViewer oldValue={'alpha\nbeta'} newValue={'alpha\ngamma'} filePath="demo.txt" />);
    expect(screen.getByText(/beta/)).toBeInTheDocument();
    expect(screen.getByText(/gamma/)).toBeInTheDocument();
  });
});
