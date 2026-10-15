/**
 * [INPUT]
 * - @testing-library/react (POS: React Component Testing)
 * - @/components/features/chat-window/three-pane-studio/ThreePaneContextStudio
 * - @/components/features/chat-window/three-pane-studio/useThreePaneStudioStore
 * - @/components/features/chat-window/three-pane-studio/threePaneStudioEngine
 *
 * [OUTPUT]
 * - Component UI unit test suite for ThreePaneContextStudio layouts, toggles, and slot rendering.
 */

import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ThreePaneContextStudio } from '../ThreePaneContextStudio';
import { useThreePaneStudioStore } from '../useThreePaneStudioStore';
import { buildDefaultContextTree } from '../threePaneStudioEngine';

describe('ThreePaneContextStudio Component', () => {
  beforeEach(() => {
    useThreePaneStudioStore.getState().resetStore();
  });

  it('should render primary three-pane layout containers', () => {
    render(<ThreePaneContextStudio />);

    expect(screen.getByTestId('three-pane-context-studio')).toBeInTheDocument();
    expect(screen.getByTestId('left-pane-container')).toBeInTheDocument();
    expect(screen.getByTestId('middle-content-pane-empty')).toBeInTheDocument();
    expect(screen.getByTestId('right-pane-container')).toBeInTheDocument();
  });

  it('should toggle left pane visibility when left collapse button is clicked', () => {
    render(<ThreePaneContextStudio />);

    const toggleLeftBtn = screen.getByTestId('btn-toggle-left-pane');
    expect(screen.getByTestId('left-pane-container')).toBeInTheDocument();

    fireEvent.click(toggleLeftBtn);
    expect(screen.queryByTestId('left-pane-container')).not.toBeInTheDocument();

    fireEvent.click(toggleLeftBtn);
    expect(screen.getByTestId('left-pane-container')).toBeInTheDocument();
  });

  it('should toggle right pane visibility when right collapse button is clicked', () => {
    render(<ThreePaneContextStudio />);

    const toggleRightBtn = screen.getByTestId('btn-toggle-right-pane');
    expect(screen.getByTestId('right-pane-container')).toBeInTheDocument();

    fireEvent.click(toggleRightBtn);
    expect(screen.queryByTestId('right-pane-container')).not.toBeInTheDocument();

    fireEvent.click(toggleRightBtn);
    expect(screen.getByTestId('right-pane-container')).toBeInTheDocument();
  });

  it('should switch between Agent Chat and Terminal views in right pane', () => {
    render(<ThreePaneContextStudio />);

    expect(screen.getByTestId('agent-chat-slot')).toBeInTheDocument();
    expect(screen.queryByTestId('terminal-slot')).not.toBeInTheDocument();

    const terminalBtn = screen.getByTestId('btn-mode-terminal');
    fireEvent.click(terminalBtn);

    expect(screen.getByTestId('terminal-slot')).toBeInTheDocument();
    expect(screen.queryByTestId('agent-chat-slot')).not.toBeInTheDocument();

    const chatBtn = screen.getByTestId('btn-mode-chat');
    fireEvent.click(chatBtn);

    expect(screen.getByTestId('agent-chat-slot')).toBeInTheDocument();
  });

  it('should render custom slot components for agent chat and terminal', () => {
    render(
      <ThreePaneContextStudio
        renderAgentChat={() => <div data-testid="custom-chat-view">Custom Agent Chat View</div>}
        renderTerminal={() => <div data-testid="custom-terminal-view">Custom Terminal View</div>}
      />,
    );

    expect(screen.getByTestId('custom-chat-view')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('btn-mode-terminal'));
    expect(screen.getByTestId('custom-terminal-view')).toBeInTheDocument();
  });

  it('should display selected node content in middle pane', () => {
    const customTree = buildDefaultContextTree({
      resources: [
        {
          id: 'index-html',
          name: 'index.html',
          path: '/workspace/index.html',
          content: '<!DOCTYPE html><html><body>Hello Studio</body></html>',
        },
      ],
    });

    const store = useThreePaneStudioStore.getState();
    store.setRootNodes(customTree);
    store.selectNode('res-index-html');

    render(<ThreePaneContextStudio />);

    expect(screen.getByTestId('middle-content-pane')).toBeInTheDocument();
    expect(screen.getByTestId('node-title')).toHaveTextContent('index.html');
    expect(screen.getByTestId('node-content-body')).toHaveTextContent('Hello Studio');
  });
});
