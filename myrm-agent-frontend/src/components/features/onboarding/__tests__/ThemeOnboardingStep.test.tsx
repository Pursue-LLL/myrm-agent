import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ButtonHTMLAttributes } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ThemeOnboardingStep from '../ThemeOnboardingStep';
import * as onboardingThemePresets from '../onboarding-theme-presets';

const mockUpdatePersonalSettings = vi.hoisted(() => vi.fn(() => Promise.resolve()));

vi.mock('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
}));

vi.mock('@/store/useConfigStore', () => ({
  default: (selector: (state: { updatePersonalSettings: typeof mockUpdatePersonalSettings }) => unknown) =>
    selector({ updatePersonalSettings: mockUpdatePersonalSettings }),
}));

vi.mock('@/components/primitives/button', () => ({
  Button: ({ children, onClick, ...rest }: ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button type="button" onClick={onClick} {...rest}>
      {children}
    </button>
  ),
}));

describe('ThemeOnboardingStep', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('persists official-default when Continue is clicked without changing selection', async () => {
    const onComplete = vi.fn();
    const onSkip = vi.fn();

    render(<ThemeOnboardingStep onComplete={onComplete} onSkip={onSkip} />);

    fireEvent.click(screen.getByRole('button', { name: 'boot.onboarding.themePick.continueButton' }));

    await waitFor(() => {
      expect(mockUpdatePersonalSettings).toHaveBeenCalledWith({
        activeThemeProfileId: 'official-default',
        themeFontOverride: 'inter',
      });
    });
    expect(onComplete).toHaveBeenCalledTimes(1);
    expect(onSkip).not.toHaveBeenCalled();
  });

  it('persists selected preset when user picks ocean then continues', async () => {
    const onComplete = vi.fn();

    render(<ThemeOnboardingStep onComplete={onComplete} onSkip={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: 'settings.appearancePanel.presets.preset-ocean' }));
    fireEvent.click(screen.getByRole('button', { name: 'boot.onboarding.themePick.continueButton' }));

    await waitFor(() => {
      expect(mockUpdatePersonalSettings).toHaveBeenCalledWith({
        activeThemeProfileId: 'preset-ocean',
        themeFontOverride: 'inter',
      });
    });
    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it('skips persistence when Keep default is clicked', () => {
    const onComplete = vi.fn();
    const onSkip = vi.fn();

    render(<ThemeOnboardingStep onComplete={onComplete} onSkip={onSkip} />);

    fireEvent.click(screen.getByRole('button', { name: 'settings.appearancePanel.presets.preset-ocean' }));
    fireEvent.click(screen.getByRole('button', { name: 'boot.onboarding.themePick.skipButton' }));

    expect(mockUpdatePersonalSettings).not.toHaveBeenCalled();
    expect(onSkip).toHaveBeenCalledTimes(1);
    expect(onComplete).not.toHaveBeenCalled();
  });

  it('completes without persisting when selected id fails validation', async () => {
    vi.spyOn(onboardingThemePresets, 'isOnboardingThemePresetId').mockReturnValue(false);

    const onComplete = vi.fn();

    render(<ThemeOnboardingStep onComplete={onComplete} onSkip={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: 'boot.onboarding.themePick.continueButton' }));

    await waitFor(() => {
      expect(onComplete).toHaveBeenCalledTimes(1);
    });
    expect(mockUpdatePersonalSettings).not.toHaveBeenCalled();
  });
});
