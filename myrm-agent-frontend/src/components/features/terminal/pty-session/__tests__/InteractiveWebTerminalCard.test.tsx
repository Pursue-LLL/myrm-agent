/**
 * Interactive Web Terminal Card Component Unit Tests
 */

import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { InteractiveWebTerminalCard } from '../InteractiveWebTerminalCard';
import { useWebTerminalPtyStore } from '../useWebTerminalPtyStore';

describe('InteractiveWebTerminalCard', () => {
  beforeEach(() => {
    useWebTerminalPtyStore.getState().resetToDefault();
  });

  it('should render terminal card with session tabs, viewport and blinking cursor', () => {
    render(<InteractiveWebTerminalCard />);

    expect(screen.getByTestId('interactive-web-terminal-card')).toBeInTheDocument();
    expect(screen.getByTestId('session-tab-pty-session-main')).toBeInTheDocument();
    expect(screen.getByTestId('terminal-viewport')).toBeInTheDocument();
    expect(screen.getByTestId('terminal-blinking-cursor')).toBeInTheDocument();
  });

  it('should create new PTY session when clicking new session button', () => {
    render(<InteractiveWebTerminalCard />);

    const newSessionBtn = screen.getByTestId('new-session-btn');
    fireEvent.click(newSessionBtn);

    const sessions = useWebTerminalPtyStore.getState().sessions;
    expect(sessions.length).toBeGreaterThanOrEqual(3);
  });

  it('should detach session and allow re-attaching via UI buttons', () => {
    render(<InteractiveWebTerminalCard />);

    // Initially active is connected, so detach button is visible
    const detachBtn = screen.getByTestId('detach-session-btn');
    expect(detachBtn).toBeInTheDocument();
    fireEvent.click(detachBtn);

    expect(useWebTerminalPtyStore.getState().sessions.find((s) => s.id === 'pty-session-main')?.isDetached).toBe(true);

    // After detach, attach button should be rendered
    const attachBtn = screen.getByTestId('attach-session-btn');
    expect(attachBtn).toBeInTheDocument();
    fireEvent.click(attachBtn);

    expect(useWebTerminalPtyStore.getState().sessions.find((s) => s.id === 'pty-session-main')?.isDetached).toBe(false);
  });

  it('should trigger quick keyboard shortcut buttons', () => {
    render(<InteractiveWebTerminalCard />);

    const ctrlCBtn = screen.getByTestId('quick-ctrl-c-btn');
    fireEvent.click(ctrlCBtn);

    const enterBtn = screen.getByTestId('quick-enter-btn');
    fireEvent.click(enterBtn);
  });

  it('should handle keyboard event input and update terminal', () => {
    render(<InteractiveWebTerminalCard />);

    const input = screen.getByTestId('terminal-hidden-input');
    fireEvent.keyDown(input, { key: 'e' });
    fireEvent.keyDown(input, { key: 'c' });
    fireEvent.keyDown(input, { key: 'h' });
    fireEvent.keyDown(input, { key: 'o' });

    expect(useWebTerminalPtyStore.getState().inputBuffer).toBe('echo');

    // Press Enter to submit
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(useWebTerminalPtyStore.getState().inputBuffer).toBe('');
  });

  it('should toggle fullscreen mode and clear buffer', () => {
    render(<InteractiveWebTerminalCard />);

    const fullscreenBtn = screen.getByTestId('toggle-fullscreen-btn');
    fireEvent.click(fullscreenBtn);
    expect(useWebTerminalPtyStore.getState().isFullscreen).toBe(true);

    const clearBtn = screen.getByTestId('clear-buffer-btn');
    fireEvent.click(clearBtn);
    expect(useWebTerminalPtyStore.getState().buffers['pty-session-main']).toHaveLength(0);
  });
});
