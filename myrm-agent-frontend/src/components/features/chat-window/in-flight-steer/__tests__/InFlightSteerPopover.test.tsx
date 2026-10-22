import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { InFlightSteerPopover } from '../InFlightSteerPopover';
import { useInFlightSteerStore } from '../useInFlightSteerStore';
import type { ActiveSubagentSwimlane } from '../inFlightSteerTypes';

vi.mock('@/services/background-tasks', () => ({
  steerBackgroundTask: vi.fn().mockResolvedValue({ message: 'ok', task_id: 't-1' }),
  cancelBackgroundTask: vi.fn().mockResolvedValue({ message: 'ok', task_id: 't-1' }),
}));

vi.mock('@/services/i18nToastService', () => ({ showI18nToast: vi.fn() }));
vi.mock('@/lib/utils/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

describe('InFlightSteerPopover', () => {
  const mockSubagent: ActiveSubagentSwimlane = {
    id: 'sub-pop-1',
    name: 'Frontend Developer',
    role: 'UI/UX',
    status: 'running',
    currentStep: 'Building Navigation Component',
    tokensUsed: 1500,
    elapsedSeconds: 24,
    taskId: 'task-pop-1',
  };

  beforeEach(() => {
    vi.clearAllMocks();
    useInFlightSteerStore.getState().clearSwimlanes();
    useInFlightSteerStore.getState().registerSwimlane(mockSubagent);
  });

  it('renders subagent info, presets, and action buttons', () => {
    const handleClose = vi.fn();
    render(<InFlightSteerPopover subagent={mockSubagent} onClose={handleClose} />);

    expect(screen.getByText('Frontend Developer')).toBeInTheDocument();
    expect(screen.getByText(/UI\/UX · Building Navigation Component/)).toBeInTheDocument();
    expect(screen.getByText('简明扼要')).toBeInTheDocument();
    expect(screen.getByText('边界防御')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('输入动态微调指令...')).toBeInTheDocument();
    expect(screen.getByText(/提前叫停/)).toBeInTheDocument();
  });

  it('triggers preset steer option when clicked and calls onClose', async () => {
    const handleClose = vi.fn();
    render(<InFlightSteerPopover subagent={mockSubagent} onClose={handleClose} />);

    const presetBtn = screen.getByRole('button', { name: '简明扼要' });
    fireEvent.click(presetBtn);

    await waitFor(() => {
      expect(handleClose).toHaveBeenCalled();
    });

    const currentSub = useInFlightSteerStore.getState().swimlanes[0];
    expect(currentSub.lastInstruction).toContain('聚焦核心结论');
  });

  it('sends custom steer instruction via button click and Enter key', async () => {
    const handleClose = vi.fn();
    render(<InFlightSteerPopover subagent={mockSubagent} onClose={handleClose} />);

    const input = screen.getByPlaceholderText('输入动态微调指令...');
    fireEvent.change(input, { target: { value: 'Switch to CSS Grid layout' } });

    const sendBtn = screen.getByLabelText('下发纠偏指令');
    fireEvent.click(sendBtn);

    await waitFor(() => {
      expect(handleClose).toHaveBeenCalled();
    });

    const currentSub = useInFlightSteerStore.getState().swimlanes[0];
    expect(currentSub.lastInstruction).toBe('Switch to CSS Grid layout');
  });

  it('stops subagent gracefully and preserves partial artifacts', async () => {
    const handleClose = vi.fn();
    render(<InFlightSteerPopover subagent={mockSubagent} onClose={handleClose} />);

    const stopBtn = screen.getByRole('button', { name: /提前叫停/ });
    fireEvent.click(stopBtn);

    await waitFor(() => {
      expect(handleClose).toHaveBeenCalled();
    });

    const currentSub = useInFlightSteerStore.getState().swimlanes[0];
    expect(currentSub.status).toBe('stopped');
    expect(currentSub.partialDeliverable).toBeDefined();
  });

  it('calls onClose when close button clicked', () => {
    const handleClose = vi.fn();
    render(<InFlightSteerPopover subagent={mockSubagent} onClose={handleClose} />);

    const closeBtn = screen.getByLabelText('关闭');
    fireEvent.click(closeBtn);

    expect(handleClose).toHaveBeenCalled();
  });
});
