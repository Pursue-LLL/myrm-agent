import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import SystemFontPicker from '../SystemFontPicker';
import { getFontStack } from '@/lib/fonts';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => {
    const map: Record<string, string> = {
      inter: 'Inter (Default)',
      system: 'System Font',
      atkinson: 'Atkinson Hyperlegible',
      popularDeveloperFonts: 'Popular Developer Fonts',
      scanAllSystemFonts: 'Scan Local Installed Fonts',
      scanningFonts: 'Scanning...',
      allInstalledFonts: 'All Local Fonts',
      selectFontPlaceholder: 'Select from local installed fonts...',
      customFontPlaceholder: 'Or enter any local font name',
      apply: 'Apply',
      activeCustomFont: 'Active Custom Font',
      resetToDefault: 'Reset',
    };
    return map[key] || key;
  },
}));

describe('SystemFontPicker & getFontStack', () => {
  it('should generate correct CSS font stack for builtin and custom fonts', () => {
    expect(getFontStack('inter')).toContain('--font-sans');
    expect(getFontStack('system')).toContain('ui-sans-serif');
    expect(getFontStack('JetBrains Mono')).toContain('"JetBrains Mono"');
    expect(getFontStack('Fira Code')).toContain('"Fira Code"');
  });

  it('should render builtin fonts and developer presets', () => {
    const onFontChange = vi.fn();
    render(<SystemFontPicker activeFontId="inter" onFontChange={onFontChange} />);

    expect(screen.getByText('Inter (Default)')).toBeInTheDocument();
    expect(screen.getByText('JetBrains Mono')).toBeInTheDocument();
    expect(screen.getByText('Fira Code')).toBeInTheDocument();

    fireEvent.click(screen.getByText('JetBrains Mono'));
    expect(onFontChange).toHaveBeenCalledWith('JetBrains Mono');
  });

  it('should allow custom font name input and submission', () => {
    const onFontChange = vi.fn();
    render(<SystemFontPicker activeFontId="inter" onFontChange={onFontChange} />);

    const input = screen.getByPlaceholderText('Or enter any local font name');
    const applyBtn = screen.getByText('Apply');

    fireEvent.change(input, { target: { value: 'SF Pro Text' } });
    fireEvent.click(applyBtn);

    expect(onFontChange).toHaveBeenCalledWith('SF Pro Text');
  });

  it('should show active custom font badge when custom font is selected', () => {
    const onFontChange = vi.fn();
    render(<SystemFontPicker activeFontId="SF Pro Text" onFontChange={onFontChange} />);

    expect(screen.getByText(/Active Custom Font/)).toBeInTheDocument();
    expect(screen.getByText(/SF Pro Text/)).toBeInTheDocument();

    const resetBtn = screen.getByText('Reset');
    fireEvent.click(resetBtn);
    expect(onFontChange).toHaveBeenCalledWith('inter');
  });
});
