import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { FleetDirectorConsole } from '../FleetDirectorConsole';
import { useFleetObserverStore } from '../useFleetObserverStore';

describe('FleetDirectorConsole', () => {
  beforeEach(() => {
    useFleetObserverStore.getState().resetState();
  });

  it('renders director console controls and injection form', () => {
    render(<FleetDirectorConsole />);

    expect(screen.getByText(/观察者导演交互控制台/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '暂停机队协同' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '单步步进机队协同' })).toBeInTheDocument();
    expect(screen.getByLabelText('目标执行节点')).toBeInTheDocument();
    expect(screen.getByLabelText('仲裁指令内容')).toBeInTheDocument();
  });

  it('toggles pause and resume buttons', () => {
    render(<FleetDirectorConsole />);

    const pauseBtn = screen.getByRole('button', { name: '暂停机队协同' });
    fireEvent.click(pauseBtn);

    const resumeBtn = screen.getByRole('button', { name: '继续运行机队' });
    expect(resumeBtn).toBeInTheDocument();
    expect(useFleetObserverStore.getState().executionMode).toBe('paused');

    fireEvent.click(resumeBtn);
    expect(screen.getByRole('button', { name: '暂停机队协同' })).toBeInTheDocument();
    expect(useFleetObserverStore.getState().executionMode).toBe('running');
  });

  it('triggers step execution on button click', () => {
    render(<FleetDirectorConsole />);

    const stepBtn = screen.getByRole('button', { name: '单步步进机队协同' });
    fireEvent.click(stepBtn);

    expect(useFleetObserverStore.getState().executionMode).toBe('stepping');
  });

  it('submits director command and displays intervention in audit log', () => {
    render(<FleetDirectorConsole />);

    const input = screen.getByLabelText('仲裁指令内容');
    fireEvent.change(input, { target: { value: '全机队立即切入稳健回滚通道' } });

    const submitBtn = screen.getByRole('button', { name: '注入指令' });
    fireEvent.click(submitBtn);

    expect(screen.getByText('全机队立即切入稳健回滚通道')).toBeInTheDocument();
    expect(screen.getByText('已强制注入')).toBeInTheDocument();

    const state = useFleetObserverStore.getState();
    expect(state.interventions.length).toBe(1);
    expect(state.interventions[0]?.commandText).toBe('全机队立即切入稳健回滚通道');
  });
});
