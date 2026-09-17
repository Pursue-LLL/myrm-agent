/** @vitest-environment jsdom */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DynamicPreferenceRadarDrawer, RadarDimensionValues } from '../DynamicPreferenceRadarDrawer';

const mockDefaultValues: RadarDimensionValues = {
  recency: 1.0,
  actionability: 1.5,
  technical_depth: 2.0,
  conciseness: 0.8,
  breadth: 1.0,
};

describe('DynamicPreferenceRadarDrawer Component', () => {
  it('returns null when isOpen is false', () => {
    const { container } = render(
      <DynamicPreferenceRadarDrawer
        isOpen={false}
        onClose={vi.fn()}
        values={mockDefaultValues}
        locked={false}
        onValueChange={vi.fn()}
        onToggleLock={vi.fn()}
        onReset={vi.fn()}
      />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders radar drawer with dimensions and SVG polygon when open', () => {
    render(
      <DynamicPreferenceRadarDrawer
        isOpen={true}
        onClose={vi.fn()}
        values={mockDefaultValues}
        locked={false}
        onValueChange={vi.fn()}
        onToggleLock={vi.fn()}
        onReset={vi.fn()}
      />
    );

    expect(screen.getByTestId('preference-radar-drawer')).toBeInTheDocument();
    expect(screen.getByTestId('radar-data-polygon')).toBeInTheDocument();
    expect(screen.getByText('在线偏好拟合雷达')).toBeInTheDocument();
    expect(screen.getByText('1.50x')).toBeInTheDocument();
    expect(screen.getByText('2.00x')).toBeInTheDocument();
  });

  it('triggers onValueChange when slider is adjusted', () => {
    const onValueChange = vi.fn();
    render(
      <DynamicPreferenceRadarDrawer
        isOpen={true}
        onClose={vi.fn()}
        values={mockDefaultValues}
        locked={false}
        onValueChange={onValueChange}
        onToggleLock={vi.fn()}
        onReset={vi.fn()}
      />
    );

    const slider = screen.getByTestId('slider-actionability');
    fireEvent.change(slider, { target: { value: '2.5' } });
    expect(onValueChange).toHaveBeenCalledWith('actionability', 2.5);
  });

  it('triggers onToggleLock when lock button is clicked', () => {
    const onToggleLock = vi.fn();
    render(
      <DynamicPreferenceRadarDrawer
        isOpen={true}
        onClose={vi.fn()}
        values={mockDefaultValues}
        locked={false}
        onValueChange={vi.fn()}
        onToggleLock={onToggleLock}
        onReset={vi.fn()}
      />
    );

    const lockBtn = screen.getByTestId('radar-toggle-lock');
    fireEvent.click(lockBtn);
    expect(onToggleLock).toHaveBeenCalledWith(true);
  });

  it('triggers onReset when reset button is clicked', () => {
    const onReset = vi.fn();
    render(
      <DynamicPreferenceRadarDrawer
        isOpen={true}
        onClose={vi.fn()}
        values={mockDefaultValues}
        locked={false}
        onValueChange={vi.fn()}
        onToggleLock={vi.fn()}
        onReset={onReset}
      />
    );

    const resetBtn = screen.getByTestId('radar-reset-button');
    fireEvent.click(resetBtn);
    expect(onReset).toHaveBeenCalledTimes(1);
  });

  it('triggers onClose when close button is clicked', () => {
    const onClose = vi.fn();
    render(
      <DynamicPreferenceRadarDrawer
        isOpen={true}
        onClose={onClose}
        values={mockDefaultValues}
        locked={false}
        onValueChange={vi.fn()}
        onToggleLock={vi.fn()}
        onReset={vi.fn()}
      />
    );

    const closeBtn = screen.getByTestId('radar-close-button');
    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('renders semantic summary banner and preset buttons', () => {
    const onSelectPreset = vi.fn();
    render(
      <DynamicPreferenceRadarDrawer
        isOpen={true}
        onClose={vi.fn()}
        values={mockDefaultValues}
        locked={false}
        onValueChange={vi.fn()}
        onToggleLock={vi.fn()}
        onReset={vi.fn()}
        onSelectPreset={onSelectPreset}
      />
    );

    expect(screen.getByText(/偏好聚焦/)).toBeInTheDocument();
    const codePresetBtn = screen.getByTestId('preset-code');
    expect(codePresetBtn).toBeInTheDocument();
    fireEvent.click(codePresetBtn);
    expect(onSelectPreset).toHaveBeenCalledWith('code');
  });
});

