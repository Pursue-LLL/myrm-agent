/** @vitest-environment jsdom */
'use client';

import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import DesktopInspectorToolbar from '../DesktopInspectorToolbar';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('DesktopInspectorToolbar Search', () => {
  const defaultProps = {
    mode: 'inspect' as const,
    onModeChange: vi.fn(),
    onRefresh: vi.fn(),
    onClose: vi.fn(),
    isRefreshing: false,
    appName: 'TextEdit',
    windowTitle: 'Untitled',
    scope: 'app' as const,
    searchQuery: '',
    onSearchQueryChange: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders search toggle button in inspect mode', () => {
    render(<DesktopInspectorToolbar {...defaultProps} />);
    const searchToggle = screen.getByRole('button', { name: 'searchPlaceholder' });
    expect(searchToggle).toBeDefined();
  });

  it('reveals search input when search toggle button is clicked', () => {
    render(<DesktopInspectorToolbar {...defaultProps} />);
    const searchToggle = screen.getByRole('button', { name: 'searchPlaceholder' });
    fireEvent.click(searchToggle);

    const input = screen.getByPlaceholderText('searchPlaceholder');
    expect(input).toBeDefined();
  });

  it('calls onSearchQueryChange when user types in search input', () => {
    const onSearchQueryChange = vi.fn();
    render(<DesktopInspectorToolbar {...defaultProps} onSearchQueryChange={onSearchQueryChange} />);

    const searchToggle = screen.getByRole('button', { name: 'searchPlaceholder' });
    fireEvent.click(searchToggle);

    const input = screen.getByPlaceholderText('searchPlaceholder');
    fireEvent.change(input, { target: { value: 'submit button' } });
    expect(onSearchQueryChange).toHaveBeenCalledWith('submit button');
  });

  it('clears query when clear button is clicked', () => {
    const onSearchQueryChange = vi.fn();
    render(
      <DesktopInspectorToolbar
        {...defaultProps}
        searchQuery="save"
        onSearchQueryChange={onSearchQueryChange}
      />
    );

    const clearButton = screen.getByRole('button', { name: 'clearSearch' });
    fireEvent.click(clearButton);
    expect(onSearchQueryChange).toHaveBeenCalledWith('');
  });
});
