/**
 * Unit tests for AvatarLockWidget component.
 *
 * [INPUT] AvatarLockWidget, AvatarMetadata
 * [OUTPUT] Full coverage for lock toggle, dice roll protection, style presets, and color selector.
 * [POS] src/components/features/agent-avatar/__tests__/AvatarLockWidget.test.tsx
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { AvatarLockWidget } from '../AvatarLockWidget';
import type { AvatarMetadata } from '../avatarTypes';

const stableT = (key: string) => {
  const translations: Record<string, string> = {
    avatarLocked: 'Avatar is locked',
    rollDice: 'Randomize Avatar',
    unlockToRoll: 'Unlock avatar to enable random dice roll',
    locked: 'Locked',
    diceRoll: 'Randomize',
    clickToUnlock: 'Click to unlock avatar',
    clickToLock: 'Click to lock avatar',
    stylePresets: 'Style Preset',
    styleBeam: 'Beam',
    stylePixel: 'Pixel',
    styleCyberpunk: 'Cyber',
    styleBauhaus: 'Bauhaus',
    backgroundTone: 'Background Tone',
  };
  return translations[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('AvatarLockWidget', () => {
  const mockMetadata: AvatarMetadata = {
    seed: 'test-seed-123',
    style: 'beam',
    backgroundColor: '#6366f1',
    isLocked: false,
    svgData: '<svg data-testid="mock-svg"></svg>',
    imageUrl: null,
  };

  it('renders SVG avatar and unlocked state correctly', () => {
    const onToggleLock = vi.fn();
    const onRollSeed = vi.fn();

    render(<AvatarLockWidget metadata={mockMetadata} onToggleLock={onToggleLock} onRollSeed={onRollSeed} />);

    expect(screen.getByTestId('avatar-lock-widget')).toBeDefined();
    expect(screen.getByText('Randomize')).toBeDefined();

    // Toggle lock button click
    const lockToggleBtn = screen.getByLabelText('Lock avatar');
    fireEvent.click(lockToggleBtn);
    expect(onToggleLock).toHaveBeenCalledTimes(1);
  });

  it('triggers onRollSeed when dice button clicked in unlocked mode', () => {
    const onRollSeed = vi.fn();
    render(<AvatarLockWidget metadata={mockMetadata} onToggleLock={vi.fn()} onRollSeed={onRollSeed} />);

    const diceBtn = screen.getByTestId('dice-roll-button');
    fireEvent.click(diceBtn);
    expect(onRollSeed).toHaveBeenCalledTimes(1);
    expect(onRollSeed.mock.calls[0][0]).toMatch(/^agent-/);
  });

  it('disables dice rolling and style/color changes when avatar is locked', () => {
    const lockedMetadata: AvatarMetadata = {
      ...mockMetadata,
      isLocked: true,
    };
    const onRollSeed = vi.fn();
    const onChangeStyle = vi.fn();
    const onChangeBgColor = vi.fn();

    render(
      <AvatarLockWidget
        metadata={lockedMetadata}
        onToggleLock={vi.fn()}
        onRollSeed={onRollSeed}
        onChangeStyle={onChangeStyle}
        onChangeBgColor={onChangeBgColor}
      />,
    );

    const diceBtn = screen.getByTestId('dice-roll-button');
    expect(diceBtn.hasAttribute('disabled')).toBe(true);
    fireEvent.click(diceBtn);
    expect(onRollSeed).not.toHaveBeenCalled();

    const pixelBtn = screen.getByText('Pixel');
    expect(pixelBtn.hasAttribute('disabled')).toBe(true);
  });

  it('triggers onChangeStyle when clicking style preset option in unlocked mode', () => {
    const onChangeStyle = vi.fn();
    render(
      <AvatarLockWidget
        metadata={mockMetadata}
        onToggleLock={vi.fn()}
        onRollSeed={vi.fn()}
        onChangeStyle={onChangeStyle}
      />,
    );

    const pixelBtn = screen.getByText('Pixel');
    fireEvent.click(pixelBtn);
    expect(onChangeStyle).toHaveBeenCalledWith('pixel');
  });

  it('triggers onChangeBgColor when clicking color swatch in unlocked mode', () => {
    const onChangeBgColor = vi.fn();
    render(
      <AvatarLockWidget
        metadata={mockMetadata}
        onToggleLock={vi.fn()}
        onRollSeed={vi.fn()}
        onChangeBgColor={onChangeBgColor}
      />,
    );

    const cyanSwatch = screen.getByLabelText('Select color #06b6d4');
    fireEvent.click(cyanSwatch);
    expect(onChangeBgColor).toHaveBeenCalledWith('#06b6d4');
  });

  it('renders image element when imageUrl is present', () => {
    const imageMetadata: AvatarMetadata = {
      ...mockMetadata,
      imageUrl: 'https://example.com/avatar.png',
    };

    render(<AvatarLockWidget metadata={imageMetadata} onToggleLock={vi.fn()} onRollSeed={vi.fn()} />);

    const img = screen.getByAltText('Agent Avatar');
    expect(img.getAttribute('src')).toBe('https://example.com/avatar.png');
  });
});
