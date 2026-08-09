/**
 * [INPUT]
 * ThemeProvider enableSystem config + Switcher button behavior.
 * [OUTPUT]
 * Vitest: theme switcher renders 3 buttons, setTheme called correctly.
 * [POS]
 * Regression guard for system theme following fix (enableSystem=true).
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const mockSetTheme = vi.fn();
const mockUseTheme = vi.fn(() => ({ theme: 'system', setTheme: mockSetTheme }));

vi.mock('next-themes', () => ({
  useTheme: () => mockUseTheme(),
}));

const stableT = (key: string) => {
  const map: Record<string, string> = {
    'themeOptions.light': 'Light',
    'themeOptions.dark': 'Dark',
    'themeOptions.system': 'System',
  };
  return map[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/lib/utils/classnameUtils', () => ({
  cn: (...args: string[]) => args.filter(Boolean).join(' '),
}));

import ThemeSwitcher from '../Switcher';

describe('ThemeSwitcher', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseTheme.mockReturnValue({ theme: 'system', setTheme: mockSetTheme });
  });

  it('renders three theme buttons', () => {
    render(<ThemeSwitcher />);
    expect(screen.getByText('Light')).toBeDefined();
    expect(screen.getByText('Dark')).toBeDefined();
    expect(screen.getByText('System')).toBeDefined();
  });

  it('calls setTheme("light") when Light clicked', () => {
    render(<ThemeSwitcher />);
    fireEvent.click(screen.getByText('Light'));
    expect(mockSetTheme).toHaveBeenCalledWith('light');
  });

  it('calls setTheme("dark") when Dark clicked', () => {
    render(<ThemeSwitcher />);
    fireEvent.click(screen.getByText('Dark'));
    expect(mockSetTheme).toHaveBeenCalledWith('dark');
  });

  it('calls setTheme("system") when System clicked', () => {
    render(<ThemeSwitcher />);
    fireEvent.click(screen.getByText('System'));
    expect(mockSetTheme).toHaveBeenCalledWith('system');
  });

  it('does NOT call setTheme on its own (no rogue useEffect)', () => {
    render(<ThemeSwitcher />);
    expect(mockSetTheme).not.toHaveBeenCalled();
  });
});
