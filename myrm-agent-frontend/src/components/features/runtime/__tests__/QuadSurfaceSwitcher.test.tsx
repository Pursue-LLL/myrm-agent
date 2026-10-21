/** @vitest-environment jsdom */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { QuadSurfaceSwitcher } from '../QuadSurfaceSwitcher';

describe('QuadSurfaceSwitcher', () => {
  it('renders all four projection surface tabs', () => {
    render(
      <QuadSurfaceSwitcher activeSurface="runtime_console" onSwitch={vi.fn()} />
    );

    expect(screen.getByRole('tab', { name: /Chat View/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Runtime Console/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Deliverables/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Audit Ledger/i })).toBeInTheDocument();
  });

  it('marks active surface with aria-selected true', () => {
    render(
      <QuadSurfaceSwitcher activeSurface="runtime_console" onSwitch={vi.fn()} />
    );

    const activeTab = screen.getByRole('tab', { name: /Runtime Console/i });
    expect(activeTab).toHaveAttribute('aria-selected', 'true');

    const inactiveTab = screen.getByRole('tab', { name: /Deliverables/i });
    expect(inactiveTab).toHaveAttribute('aria-selected', 'false');
  });

  it('triggers onSwitch when clicking a different tab', () => {
    const handleSwitch = vi.fn();
    render(
      <QuadSurfaceSwitcher activeSurface="runtime_console" onSwitch={handleSwitch} />
    );

    const deliverablesTab = screen.getByRole('tab', { name: /Deliverables/i });
    fireEvent.click(deliverablesTab);

    expect(handleSwitch).toHaveBeenCalledTimes(1);
    expect(handleSwitch).toHaveBeenCalledWith('deliverables');
  });
});
