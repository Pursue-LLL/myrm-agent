/** @vitest-environment jsdom */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import { PreferenceRadarToggle } from '../PreferenceRadarToggle';

vi.mock('@/services/memory/preferences', () => ({
  getPreferenceRadarState: vi.fn().mockResolvedValue({
    session_id: 'session-123',
    dimensions: {
      recency: 1.0,
      actionability: 1.5,
      technical_depth: 2.0,
      conciseness: 1.0,
      breadth: 1.0,
    },
    locked: false,
  }),
  tunePreferenceRadar: vi.fn().mockResolvedValue({ success: true }),
  RADAR_PRESETS: {
    balanced: {
      label: '平衡通用',
      values: { recency: 1.0, actionability: 1.0, technical_depth: 1.0, conciseness: 1.0, breadth: 1.0 },
    },
    code: {
      label: '编码实战',
      values: { recency: 1.5, actionability: 2.5, technical_depth: 2.0, conciseness: 1.8, breadth: 0.5 },
    },
    research: {
      label: '调研推演',
      values: { recency: 2.0, actionability: 0.5, technical_depth: 2.5, conciseness: 0.8, breadth: 2.5 },
    },
  },
}));

describe('PreferenceRadarToggle', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders satellite button and toggles drawer on click', async () => {
    await act(async () => {
      render(<PreferenceRadarToggle chatId="session-123" />);
    });

    const toggleBtn = screen.getByTestId('preference-radar-toggle-button');
    expect(toggleBtn).toBeInTheDocument();

    // Drawer is closed initially
    expect(screen.queryByTestId('preference-radar-drawer')).toBeNull();

    // Click to open drawer
    await act(async () => {
      fireEvent.click(toggleBtn);
    });
    await waitFor(() => {
      expect(screen.getByTestId('preference-radar-drawer')).toBeInTheDocument();
    });

    // Click again to close drawer
    await act(async () => {
      fireEvent.click(toggleBtn);
    });
    await waitFor(() => {
      expect(screen.queryByTestId('preference-radar-drawer')).toBeNull();
    });
  });

  it('handles API error gracefully and falls back to default values without crashing', async () => {
    const { getPreferenceRadarState } = await import('@/services/memory/preferences');
    vi.mocked(getPreferenceRadarState).mockRejectedValueOnce(new Error('Network error 500'));

    await act(async () => {
      render(<PreferenceRadarToggle chatId="session-error" />);
    });

    const toggleBtn = screen.getByTestId('preference-radar-toggle-button');
    expect(toggleBtn).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(toggleBtn);
    });

    await waitFor(() => {
      expect(screen.getByTestId('preference-radar-drawer')).toBeInTheDocument();
    });
  });

  it('refetches preference state when chatId changes (session switch)', async () => {
    const { getPreferenceRadarState } = await import('@/services/memory/preferences');

    const { rerender } = render(<PreferenceRadarToggle chatId="session-a" />);
    expect(getPreferenceRadarState).toHaveBeenCalledWith('session-a');

    rerender(<PreferenceRadarToggle chatId="session-b" />);
    await waitFor(() => {
      expect(getPreferenceRadarState).toHaveBeenCalledWith('session-b');
    });
  });
});
