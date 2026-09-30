/**
 * Unit tests for CompactionAnchorStrip.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { CompactionAnchorStrip, type ExactAnchorData } from '../CompactionAnchorStrip';

describe('CompactionAnchorStrip', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn(),
      },
    });
  });

  it('renders nothing when anchors are empty', () => {
    const { container } = render(<CompactionAnchorStrip anchors={{}} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders header with symbol count and collapsed badges', () => {
    const mockAnchors: ExactAnchorData = {
      commitShas: ['abcdef1234567890'],
      filePaths: ['src/core/engine.ts'],
      codeSymbols: ['AnchorIndex'],
    };

    render(<CompactionAnchorStrip anchors={mockAnchors} />);

    expect(screen.getByText('Verified Anchors')).toBeInTheDocument();
    expect(screen.getByText('3 symbols')).toBeInTheDocument();
    expect(screen.getByText('abcdef1')).toBeInTheDocument();
    expect(screen.getByText('engine.ts')).toBeInTheDocument();
    expect(screen.getByText('AnchorIndex')).toBeInTheDocument();
  });

  it('toggles expand and collapse view on button click', () => {
    const mockAnchors: ExactAnchorData = {
      commitShas: ['abcdef1234567890'],
      filePaths: ['src/core/engine.ts'],
      errorSpans: ['SyntaxError: unexpected token'],
    };

    render(<CompactionAnchorStrip anchors={mockAnchors} />);

    const toggleBtn = screen.getByRole('button', { name: /expand anchors/i });
    expect(toggleBtn).toBeInTheDocument();

    // Click to expand
    fireEvent.click(toggleBtn);
    expect(screen.getByText('Commits (1)')).toBeInTheDocument();
    expect(screen.getByText('Files (1)')).toBeInTheDocument();
    expect(screen.getByText('Error Signatures (1)')).toBeInTheDocument();
    expect(screen.getByText('SyntaxError: unexpected token')).toBeInTheDocument();

    // Click to collapse
    const collapseBtn = screen.getByRole('button', { name: /collapse anchors/i });
    fireEvent.click(collapseBtn);
    expect(screen.queryByText('Commits (1)')).not.toBeInTheDocument();
  });

  it('handles copying and triggers symbol click callback', () => {
    const onSymbolClick = vi.fn();
    const mockAnchors: ExactAnchorData = {
      filePaths: ['src/utils/math.ts'],
      codeSymbols: ['calculateSum'],
    };

    render(<CompactionAnchorStrip anchors={mockAnchors} onSymbolClick={onSymbolClick} />);

    // Expand
    fireEvent.click(screen.getByRole('button', { name: /expand anchors/i }));

    // Click the file symbol button
    const fileBtn = screen.getByTitle('Click to copy path');
    fireEvent.click(fileBtn);

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('src/utils/math.ts');
    expect(onSymbolClick).toHaveBeenCalledWith('src/utils/math.ts', 'filePaths');
  });
});
