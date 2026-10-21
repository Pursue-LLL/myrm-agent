import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { TooltipProvider } from '@/components/primitives/tooltip';
import { PinToDashboardButton } from '../PinToDashboardButton';
import { useDashboardWorkspaceStore } from '../useDashboardWorkspaceStore';

const renderWithProvider = (ui: React.ReactElement) => {
  return render(<TooltipProvider>{ui}</TooltipProvider>);
};

describe('PinToDashboardButton', () => {
  beforeEach(() => {
    useDashboardWorkspaceStore.getState().clearAllWidgets();
  });

  it('renders unpinned state initially with correct tooltip and icon', () => {
    renderWithProvider(
      <PinToDashboardButton
        widgetId="test-widget-1"
        title="Test Widget"
        language="html"
        content="<div>Test</div>"
      />,
    );

    const button = screen.getByTestId('pin-to-dashboard-btn');
    expect(button).toBeInTheDocument();
    expect(button).toHaveAttribute('aria-label', '固定到工作台 Dashboard');
  });

  it('pins widget on click and changes state to pinned', () => {
    renderWithProvider(
      <PinToDashboardButton
        widgetId="test-widget-2"
        title="Revenue Chart"
        language="svg"
        content="<svg></svg>"
      />,
    );

    const button = screen.getByTestId('pin-to-dashboard-btn');
    fireEvent.click(button);

    // State in store updated
    expect(useDashboardWorkspaceStore.getState().isWidgetPinned('test-widget-2')).toBe(true);
    expect(useDashboardWorkspaceStore.getState().widgets[0].title).toBe('Revenue Chart');

    // Button label reflects pinned state
    expect(button).toHaveAttribute('aria-label', '已固定至工作台 (点击取消)');
  });

  it('unpins widget when clicked again', () => {
    useDashboardWorkspaceStore.getState().pinWidget({
      id: 'test-widget-3',
      title: 'Already Pinned',
      language: 'html',
      content: '<p>Content</p>',
    });

    renderWithProvider(
      <PinToDashboardButton
        widgetId="test-widget-3"
        title="Already Pinned"
        language="html"
        content="<p>Content</p>"
      />,
    );

    const button = screen.getByTestId('pin-to-dashboard-btn');
    expect(button).toHaveAttribute('aria-label', '已固定至工作台 (点击取消)');

    fireEvent.click(button);

    expect(useDashboardWorkspaceStore.getState().isWidgetPinned('test-widget-3')).toBe(false);
    expect(button).toHaveAttribute('aria-label', '固定到工作台 Dashboard');
  });

  it('stops event propagation on click', () => {
    const parentClickHandler = vi.fn();

    renderWithProvider(
      <div role="toolbar" tabIndex={0} onClick={parentClickHandler} onKeyDown={() => {}}>
        <PinToDashboardButton
          widgetId="test-widget-4"
          title="Prop Widget"
          content="<span>Test</span>"
        />
      </div>,
    );

    const button = screen.getByTestId('pin-to-dashboard-btn');
    fireEvent.click(button);

    expect(parentClickHandler).not.toHaveBeenCalled();
  });

  it('renders optional text label when showText is true', () => {
    const { rerender } = renderWithProvider(
      <PinToDashboardButton
        widgetId="test-widget-5"
        title="Text Widget"
        content="<div>Text</div>"
        showText={true}
      />,
    );

    expect(screen.getByText('固定')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('pin-to-dashboard-btn'));

    rerender(
      <TooltipProvider>
        <PinToDashboardButton
          widgetId="test-widget-5"
          title="Text Widget"
          content="<div>Text</div>"
          showText={true}
        />
      </TooltipProvider>,
    );

    expect(screen.getByText('已固定')).toBeInTheDocument();
  });
});
