import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import {
  AutonomousLoopModePill,
  AutonomousLoopStateData,
} from '../AutonomousLoopModePill';

describe('AutonomousLoopModePill', () => {
  const cruisingSample: AutonomousLoopStateData = {
    session_id: 'chat_01',
    goal_id: 'goal_autonomous_search',
    mode: 'autonomous',
    current_step: 3,
    max_steps: 10,
    is_active: true,
    history: [
      {
        step_index: 1,
        action_type: 'researcher_spawn',
        description: 'Spawned Researcher agent',
        status: 'success',
        timestamp: '2026-10-15T12:00:00Z',
      },
      {
        step_index: 2,
        action_type: 'web_search',
        description: 'Queried multi-agent benchmarks',
        status: 'success',
        timestamp: '2026-10-15T12:01:00Z',
      },
      {
        step_index: 3,
        action_type: 'summarize_findings',
        description: 'Generated intermediate synthesis',
        status: 'success',
        timestamp: '2026-10-15T12:02:00Z',
      },
    ],
    started_at: '2026-10-15T12:00:00Z',
    last_advanced_at: '2026-10-15T12:02:00Z',
  };

  const pausedSample: AutonomousLoopStateData = {
    session_id: 'chat_02',
    goal_id: 'goal_prod_deployment',
    mode: 'paused',
    current_step: 5,
    max_steps: 5,
    is_active: false,
    history: [
      {
        step_index: 5,
        action_type: 'deploy_cluster',
        description: 'Cloud formation template deployment',
        status: 'paused',
        timestamp: '2026-10-15T12:10:00Z',
      },
    ],
    pause_reason: 'Max autonomous steps limit reached',
    started_at: '2026-10-15T12:00:00Z',
    last_advanced_at: '2026-10-15T12:10:00Z',
  };

  it('renders autonomous cruising state with step budget and progress', () => {
    render(
      <AutonomousLoopModePill
        chatId="chat_01"
        loopState={cruisingSample}
      />,
    );

    expect(screen.getByText(/Autonomous Cruise/i)).toBeInTheDocument();
    expect(screen.getByText(/Step 3 \/ 10/i)).toBeInTheDocument();
    expect(screen.getByText(/30%/i)).toBeInTheDocument();
    expect(screen.getByText(/Goal: goal_autonomous_search/i)).toBeInTheDocument();
  });

  it('triggers onSetMode when switching to supervised pacing', () => {
    const handleSetMode = vi.fn();
    render(
      <AutonomousLoopModePill
        chatId="chat_01"
        loopState={cruisingSample}
        onSetMode={handleSetMode}
      />,
    );

    const superviseBtn = screen.getByRole('button', { name: /switch to supervised pacing/i });
    fireEvent.click(superviseBtn);
    expect(handleSetMode).toHaveBeenCalledWith('supervised');
  });

  it('renders paused watchdog alert banner when intervention is needed', () => {
    render(
      <AutonomousLoopModePill
        chatId="chat_02"
        loopState={pausedSample}
      />,
    );

    expect(screen.getByText(/Watchdog Paused/i)).toBeInTheDocument();
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText(/Max autonomous steps limit reached/i)).toBeInTheDocument();
  });

  it('triggers onAdvanceStep when step button clicked', () => {
    const handleAdvance = vi.fn();
    render(
      <AutonomousLoopModePill
        chatId="chat_01"
        loopState={cruisingSample}
        onAdvanceStep={handleAdvance}
      />,
    );

    const stepBtn = screen.getByRole('button', { name: /advance single step/i });
    fireEvent.click(stepBtn);
    expect(handleAdvance).toHaveBeenCalledTimes(1);
  });

  it('toggles audit history trail dropdown', () => {
    render(
      <AutonomousLoopModePill
        chatId="chat_01"
        loopState={cruisingSample}
      />,
    );

    expect(screen.queryByTestId('autonomous-loop-history')).not.toBeInTheDocument();

    const historyToggle = screen.getByRole('button', { name: /toggle execution history/i });
    fireEvent.click(historyToggle);

    expect(screen.getByTestId('autonomous-loop-history')).toBeInTheDocument();
    expect(screen.getByText(/Step Audit Trail \(3\)/i)).toBeInTheDocument();
    expect(screen.getByText(/researcher_spawn/i)).toBeInTheDocument();
    expect(screen.getByText(/web_search/i)).toBeInTheDocument();
  });

  it('triggers onCompleteLoop and onDismiss callbacks', () => {
    const handleComplete = vi.fn();
    const handleDismiss = vi.fn();
    render(
      <AutonomousLoopModePill
        chatId="chat_01"
        loopState={cruisingSample}
        onCompleteLoop={handleComplete}
        onDismiss={handleDismiss}
      />,
    );

    const doneBtn = screen.getByRole('button', { name: /mark goal complete/i });
    fireEvent.click(doneBtn);
    expect(handleComplete).toHaveBeenCalledTimes(1);

    const dismissBtn = screen.getByRole('button', { name: /dismiss autonomous loop card/i });
    fireEvent.click(dismissBtn);
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });
});
