/** @vitest-environment jsdom */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { AdaptiveMultiPanelGrid } from '../AdaptiveMultiPanelGrid';

describe('AdaptiveMultiPanelGrid Component', () => {
  const renderGrid = (overridePosture?: 'foldable-expanded' | 'mobile-landscape' | 'mobile-portrait' | 'desktop') =>
    render(
      <AdaptiveMultiPanelGrid
        leftPanel={<div data-testid="chat-panel">聊天与审批流</div>}
        rightPanel={<div data-testid="terminal-panel">PTY 终端视口</div>}
        thirdPanel={<div data-testid="third-panel">扩展三栏面板</div>}
        overridePosture={overridePosture}
      />,
    );

  it('renders dual panels with golden ratio banner in foldable-expanded posture (8:7)', () => {
    renderGrid('foldable-expanded');

    expect(screen.getByTestId('adaptive-grid-foldable')).toBeDefined();
    expect(screen.getByTestId('chat-panel')).toBeDefined();
    expect(screen.getByTestId('terminal-panel')).toBeDefined();
    expect(screen.getByText(/黄金双栏|foldableGolden/i)).toBeDefined();
  });

  it('renders slim dual panels in mobile-landscape posture', () => {
    renderGrid('mobile-landscape');

    expect(screen.getByTestId('adaptive-grid-mobile-landscape')).toBeDefined();
    expect(screen.getByTestId('chat-panel')).toBeDefined();
    expect(screen.getByTestId('terminal-panel')).toBeDefined();
    expect(screen.getByText(/手机横屏|mobileLandscape/i)).toBeDefined();
  });

  it('renders stacked single panel with tab toggling in mobile-portrait posture', () => {
    renderGrid('mobile-portrait');

    expect(screen.getByTestId('adaptive-grid-mobile-portrait')).toBeDefined();
    // Default left panel is visible
    expect(screen.getByTestId('chat-panel')).toBeDefined();
    expect(screen.queryByTestId('terminal-panel')).toBeNull();

    // Toggle to right panel
    const tabRight = screen.getByTestId('mobile-tab-right');
    fireEvent.click(tabRight);

    expect(screen.queryByTestId('chat-panel')).toBeNull();
    expect(screen.getByTestId('terminal-panel')).toBeDefined();
  });

  it('renders desktop multi-panel grid with draggable separator and collapse controls', () => {
    renderGrid('desktop');

    expect(screen.getByTestId('adaptive-grid-desktop')).toBeDefined();
    expect(screen.getByTestId('grid-splitter')).toBeDefined();

    // Collapse right panel
    const collapseBtn = screen.getByRole('button', { name: /collapsePanel|折叠面板/i });
    fireEvent.click(collapseBtn);

    // Expand button appears
    const expandBtn = screen.getByRole('button', { name: /expandPanel|展开面板/i });
    expect(expandBtn).toBeDefined();

    // Click expand restores right panel
    fireEvent.click(expandBtn);
    expect(screen.getByTestId('terminal-panel')).toBeDefined();
  });

  it('renders optional third panel on desktop', () => {
    renderGrid('desktop');
    expect(screen.getByTestId('third-panel')).toBeDefined();
  });
});
