/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LiquidVibrancyStatusHub } from '../LiquidVibrancyStatusHub';

const stableT = (key: string, options?: { platform?: string }) => {
    if (key === 'platformTag' && options?.platform) {
      return `${options.platform} Native Vibrancy`;
    }
    return key;
  };

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('LiquidVibrancyStatusHub component', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.style.removeProperty('--desktop-vibrancy-blur');
    document.documentElement.style.removeProperty('--desktop-vibrancy-saturate');
    document.documentElement.classList.remove('vibrancy-disabled');
  });

  it('renders floating HUD pill with accessible label and shortcut', () => {
    render(<LiquidVibrancyStatusHub />);
    const pill = screen.getByLabelText('triggerAriaLabel');
    expect(pill).toBeInTheDocument();
    expect(screen.getByText('⌥⌘V')).toBeInTheDocument();
  });

  it('toggles tuner popover when HUD pill is clicked', () => {
    render(<LiquidVibrancyStatusHub />);
    const pill = screen.getByLabelText('triggerAriaLabel');

    // Popover is initially closed
    expect(screen.queryByText('panelTitle')).not.toBeInTheDocument();

    // Click to open
    fireEvent.click(pill);
    expect(screen.getByText('panelTitle')).toBeInTheDocument();
    expect(screen.getByText(/Native Vibrancy/)).toBeInTheDocument();

    // Click to close
    fireEvent.click(pill);
    expect(screen.queryByText('panelTitle')).not.toBeInTheDocument();
  });

  it('switches vibrancy style when option button is clicked', () => {
    render(<LiquidVibrancyStatusHub />);
    const pill = screen.getByLabelText('triggerAriaLabel');
    fireEvent.click(pill);

    const acrylicBtn = screen.getByText('styleAcrylic');
    fireEvent.click(acrylicBtn);

    expect(localStorage.getItem('myrm:vibrancy-style')).toBe('acrylic');
  });

  it('toggles blur via switch in tuner popover', () => {
    render(<LiquidVibrancyStatusHub />);
    const pill = screen.getByLabelText('triggerAriaLabel');
    fireEvent.click(pill);

    const switchBtn = screen.getByRole('switch');
    expect(switchBtn).toHaveAttribute('aria-checked', 'true');

    fireEvent.click(switchBtn);
    expect(switchBtn).toHaveAttribute('aria-checked', 'false');
    expect(localStorage.getItem('myrm:vibrancy-style')).toBe('disabled');
  });

  it('changes blur intensity via range slider', () => {
    render(<LiquidVibrancyStatusHub />);
    const pill = screen.getByLabelText('triggerAriaLabel');
    fireEvent.click(pill);

    const slider = screen.getByRole('slider');
    fireEvent.change(slider, { target: { value: '60' } });

    expect(screen.getByText('60%')).toBeInTheDocument();
    expect(localStorage.getItem('myrm:vibrancy-intensity')).toBe('60');
  });

  it('closes popover on outside click', () => {
    render(
      <div>
        <div data-testid="outside-area">Outside</div>
        <LiquidVibrancyStatusHub />
      </div>,
    );

    const pill = screen.getByLabelText('triggerAriaLabel');
    fireEvent.click(pill);
    expect(screen.getByText('panelTitle')).toBeInTheDocument();

    // Click outside
    fireEvent.mouseDown(screen.getByTestId('outside-area'));
    expect(screen.queryByText('panelTitle')).not.toBeInTheDocument();
  });
});
