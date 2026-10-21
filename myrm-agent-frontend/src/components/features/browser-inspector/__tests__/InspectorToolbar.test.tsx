/** @vitest-environment jsdom */
'use client';

import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import InspectorToolbar from '../InspectorToolbar';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('InspectorToolbar', () => {
  const defaultProps = {
    mode: 'view' as const,
    onModeChange: vi.fn(),
    onClose: vi.fn(),
    onRefresh: vi.fn(),
    pageUrl: 'https://example.com',
    pageTitle: 'Example Domain',
    isLoading: false,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders url, title, and standard controls', () => {
    render(<InspectorToolbar {...defaultProps} />);
    expect(screen.getByText('Example Domain')).toBeDefined();
    const link = screen.getByTitle('https://example.com');
    expect(link.getAttribute('href')).toBe('https://example.com');
  });

  it('renders visual desktop takeover button and dispatches open_visual_desktop event and closes inspector on click', () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
    render(<InspectorToolbar {...defaultProps} />);

    const takeoverBtn = screen.getByTestId('inspector-takeover-desktop-button');
    expect(takeoverBtn).toBeDefined();

    fireEvent.click(takeoverBtn);

    expect(dispatchSpy).toHaveBeenCalledTimes(1);
    const dispatchedEvent = dispatchSpy.mock.calls[0][0] as CustomEvent;
    expect(dispatchedEvent.type).toBe('open_visual_desktop');
    expect(defaultProps.onClose).toHaveBeenCalledTimes(1);
  });

  it('calls onClose when close button is clicked', () => {
    const onClose = vi.fn();
    render(<InspectorToolbar {...defaultProps} onClose={onClose} />);

    const closeBtn = screen.getByTitle('close');
    fireEvent.click(closeBtn);

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
