/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { TurboProTierSelector } from '../TurboProTierSelector';
import { useWorkLayoutStore } from '@/store/useWorkLayoutStore';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('TurboProTierSelector component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useWorkLayoutStore.setState({
      computeTier: 'turbo',
    });
  });

  it('renders compact mode with turbo and pro button options', () => {
    render(<TurboProTierSelector variant="compact" />);

    const turboBtn = screen.getByRole('button', { name: /computeTierTurbo/i });
    const proBtn = screen.getByRole('button', { name: /computeTierPro/i });

    expect(turboBtn).toBeDefined();
    expect(proBtn).toBeDefined();
    expect(turboBtn.getAttribute('aria-pressed')).toBe('true');
    expect(proBtn.getAttribute('aria-pressed')).toBe('false');
  });

  it('selects pro tier and dispatches custom event', () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
    render(<TurboProTierSelector variant="compact" />);

    const proBtn = screen.getByRole('button', { name: /computeTierPro/i });
    fireEvent.click(proBtn);

    expect(useWorkLayoutStore.getState().computeTier).toBe('pro');
    expect(dispatchSpy).toHaveBeenCalled();
    const event = dispatchSpy.mock.calls[0][0] as CustomEvent;
    expect(event.type).toBe('myrm:compute-tier-changed');
    expect(event.detail.tier).toBe('pro');
  });

  it('renders dropdown variant and selects an option', () => {
    render(<TurboProTierSelector variant="dropdown" />);

    const dropdownTrigger = screen.getByRole('button', { name: /computeTierTurbo/i });
    expect(dropdownTrigger).toBeDefined();

    // Open dropdown
    fireEvent.click(dropdownTrigger);

    const proOptionButtons = screen.getAllByRole('button', { name: /computeTierPro/i });
    expect(proOptionButtons.length).toBeGreaterThan(0);

    fireEvent.click(proOptionButtons[0]);
    expect(useWorkLayoutStore.getState().computeTier).toBe('pro');
  });
});
