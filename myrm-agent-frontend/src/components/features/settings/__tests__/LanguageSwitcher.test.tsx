import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { locales } from '@/i18n/config';
import { normalizeLocaleForBackend } from '@/lib/utils/locale';

const kit = vi.hoisted(() => ({
  setLocale: vi.fn(),
  persistLocaleToPersonalSettings: vi.fn(async () => undefined),
}));

vi.mock('@/i18n', () => ({ setLocale: kit.setLocale }));
vi.mock('@/lib/locale-personal-sync', () => ({
  persistLocaleToPersonalSettings: kit.persistLocaleToPersonalSettings,
}));

import LanguageSwitcher from '../LanguageSwitcher';

beforeEach(() => {
  vi.clearAllMocks();
});

describe('LanguageSwitcher', () => {
  it('offers exactly the locales the app ships, in config order', () => {
    render(<LanguageSwitcher />);

    expect(screen.getAllByRole('button')).toHaveLength(locales.length);
    expect(screen.getAllByRole('button').map((button) => button.textContent)).toEqual([
      'languageOptions.chinese',
      'languageOptions.english',
    ]);
  });

  it('marks the active locale', () => {
    render(<LanguageSwitcher />);

    expect(screen.getByRole('button', { name: 'languageOptions.english' })).toHaveClass('bg-primary');
    expect(screen.getByRole('button', { name: 'languageOptions.chinese' })).not.toHaveClass('bg-primary');
  });

  it('switches the interface and saves the choice for the agent', async () => {
    render(<LanguageSwitcher />);

    fireEvent.click(screen.getByRole('button', { name: 'languageOptions.chinese' }));

    expect(kit.setLocale).toHaveBeenCalledExactlyOnceWith('zh');
    await vi.waitFor(() => expect(kit.persistLocaleToPersonalSettings).toHaveBeenCalledExactlyOnceWith('zh'));
  });
});

/**
 * Test LanguageSwitcher personalSettings update logic
 * Logic: when language changes, update personalSettings with normalized locale
 */
describe('LanguageSwitcher - personalSettings update logic', () => {
  it('should normalize zh to zh-CN when updating personalSettings', () => {
    expect(normalizeLocaleForBackend('zh')).toBe('zh-CN');
  });

  it('should keep en as-is when updating personalSettings', () => {
    expect(normalizeLocaleForBackend('en')).toBe('en');
  });

  it('should pass through a saved locale the switcher no longer offers', () => {
    expect(normalizeLocaleForBackend('fr')).toBe('fr');
  });
});
