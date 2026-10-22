/** @vitest-environment jsdom */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { MobileAgentActionBar } from '../MobileAgentActionBar';

describe('MobileAgentActionBar Component', () => {
  it('renders all action buttons properly', () => {
    render(
      <MobileAgentActionBar
        onOpenVoice={vi.fn()}
        onOpenSkills={vi.fn()}
        onStopAgent={vi.fn()}
        onToggleSessions={vi.fn()}
      />,
    );

    expect(screen.getByTestId('action-voice-btn')).toBeDefined();
    expect(screen.getByTestId('action-skills-btn')).toBeDefined();
    expect(screen.getByTestId('action-stop-btn')).toBeDefined();
    expect(screen.getByTestId('action-sessions-btn')).toBeDefined();
  });

  it('triggers onOpenVoice when voice button is tapped', () => {
    const onOpenVoiceMock = vi.fn();

    render(
      <MobileAgentActionBar
        onOpenVoice={onOpenVoiceMock}
        onOpenSkills={vi.fn()}
        onStopAgent={vi.fn()}
        onToggleSessions={vi.fn()}
      />,
    );

    const voiceBtn = screen.getByTestId('action-voice-btn');
    fireEvent.click(voiceBtn);
    expect(onOpenVoiceMock).toHaveBeenCalledTimes(1);
  });

  it('triggers onOpenSkills when skills button is tapped', () => {
    const onOpenSkillsMock = vi.fn();

    render(
      <MobileAgentActionBar
        onOpenVoice={vi.fn()}
        onOpenSkills={onOpenSkillsMock}
        onStopAgent={vi.fn()}
        onToggleSessions={vi.fn()}
      />,
    );

    const skillsBtn = screen.getByTestId('action-skills-btn');
    fireEvent.click(skillsBtn);
    expect(onOpenSkillsMock).toHaveBeenCalledTimes(1);
  });

  it('triggers onStopAgent when isRunning is true and stop button is tapped', () => {
    const onStopAgentMock = vi.fn();

    render(
      <MobileAgentActionBar
        onOpenVoice={vi.fn()}
        onOpenSkills={vi.fn()}
        onStopAgent={onStopAgentMock}
        onToggleSessions={vi.fn()}
        isRunning={true}
      />,
    );

    const stopBtn = screen.getByTestId('action-stop-btn');
    expect((stopBtn as HTMLButtonElement).disabled).toBe(false);

    fireEvent.click(stopBtn);
    expect(onStopAgentMock).toHaveBeenCalledTimes(1);
  });

  it('disables stop button when not running', () => {
    const onStopAgentMock = vi.fn();

    render(
      <MobileAgentActionBar
        onOpenVoice={vi.fn()}
        onOpenSkills={vi.fn()}
        onStopAgent={onStopAgentMock}
        onToggleSessions={vi.fn()}
        isRunning={false}
      />,
    );

    const stopBtn = screen.getByTestId('action-stop-btn');
    expect((stopBtn as HTMLButtonElement).disabled).toBe(true);

    fireEvent.click(stopBtn);
    expect(onStopAgentMock).not.toHaveBeenCalled();
  });

  it('triggers onToggleSessions when sessions button is tapped', () => {
    const onToggleSessionsMock = vi.fn();

    render(
      <MobileAgentActionBar
        onOpenVoice={vi.fn()}
        onOpenSkills={vi.fn()}
        onStopAgent={vi.fn()}
        onToggleSessions={onToggleSessionsMock}
      />,
    );

    const sessionsBtn = screen.getByTestId('action-sessions-btn');
    fireEvent.click(sessionsBtn);
    expect(onToggleSessionsMock).toHaveBeenCalledTimes(1);
  });
});
