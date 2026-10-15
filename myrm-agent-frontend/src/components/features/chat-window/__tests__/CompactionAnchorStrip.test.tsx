/**
 * Unit tests for CompactionAnchorStrip.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { CompactionAnchorStrip, type ExactAnchorData } from '../CompactionAnchorStrip';

// 带参数回显：同时验证翻译键与插值参数
const stableT = (key: string, values?: Record<string, unknown>) => (values ? `${key}:${JSON.stringify(values)}` : key);

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

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

    expect(screen.getByText('title')).toBeInTheDocument();
    expect(screen.getByText('symbolCount:{"count":3}')).toBeInTheDocument();
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

    const toggleBtn = screen.getByRole('button', { name: 'expandAnchors' });
    expect(toggleBtn).toBeInTheDocument();

    // Click to expand
    fireEvent.click(toggleBtn);
    expect(screen.getByText('commits:{"count":1}')).toBeInTheDocument();
    expect(screen.getByText('files:{"count":1}')).toBeInTheDocument();
    expect(screen.getByText('errorSignatures:{"count":1}')).toBeInTheDocument();
    expect(screen.getByText('SyntaxError: unexpected token')).toBeInTheDocument();

    // Click to collapse
    const collapseBtn = screen.getByRole('button', { name: 'collapseAnchors' });
    fireEvent.click(collapseBtn);
    expect(screen.queryByText('commits:{"count":1}')).not.toBeInTheDocument();
  });

  it('handles copying and triggers symbol click callback', () => {
    const onSymbolClick = vi.fn();
    const mockAnchors: ExactAnchorData = {
      filePaths: ['src/utils/math.ts'],
      codeSymbols: ['calculateSum'],
    };

    render(<CompactionAnchorStrip anchors={mockAnchors} onSymbolClick={onSymbolClick} />);

    // Expand
    fireEvent.click(screen.getByRole('button', { name: 'expandAnchors' }));

    // Click the file symbol button
    const fileBtn = screen.getByTitle('copyPath');
    fireEvent.click(fileBtn);

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('src/utils/math.ts');
    expect(onSymbolClick).toHaveBeenCalledWith('src/utils/math.ts', 'filePaths');
  });

  it('labels every copy button with a translated, target-specific accessible name', () => {
    render(
      <CompactionAnchorStrip
        anchors={{
          commitShas: ['abcdef1234567890'],
          filePaths: ['src/a.ts'],
          codeSymbols: ['sym'],
          apiEndpoints: ['/v1/items'],
        }}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'expandAnchors' }));

    expect(screen.getByTitle('copySha')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'copyPathLabel:{"path":"src/a.ts"}' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'copySymbolLabel:{"symbol":"sym"}' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'copyEndpointLabel:{"endpoint":"/v1/items"}' })).toBeInTheDocument();
  });

  it('summarises how many anchors are hidden in the collapsed preview', () => {
    const filePaths = Array.from({ length: 8 }, (_, i) => `src/file${i}.ts`);

    render(<CompactionAnchorStrip anchors={{ filePaths }} />);

    expect(screen.getByText('more:{"count":2}')).toBeInTheDocument();
  });
});
