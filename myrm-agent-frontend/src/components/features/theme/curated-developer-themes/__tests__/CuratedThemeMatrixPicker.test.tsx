import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { CuratedThemeMatrixPicker } from '../CuratedThemeMatrixPicker';
import { useCuratedThemeStore } from '../useCuratedThemeStore';

describe('CuratedThemeMatrixPicker', () => {
  beforeEach(() => {
    useCuratedThemeStore.getState().resetToDefault();
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it('renders matrix header and all 6 theme cards', () => {
    render(<CuratedThemeMatrixPicker />);
    expect(screen.getByText('经典开发者暗色主题矩阵')).toBeDefined();
    expect(screen.getByText('Tokyo Night')).toBeDefined();
    expect(screen.getByText('Catppuccin Mocha')).toBeDefined();
    expect(screen.getByText('Gruvbox Dark')).toBeDefined();
    expect(screen.getByText('Nord')).toBeDefined();
    expect(screen.getByText('Dracula Pro')).toBeDefined();
    expect(screen.getByText('Cyberpunk Neon')).toBeDefined();
  });

  it('selects theme when clicking a theme card and invokes callback', () => {
    const onThemeSelect = vi.fn();
    render(<CuratedThemeMatrixPicker onThemeSelect={onThemeSelect} />);

    const tokyoCard = screen.getByRole('button', { name: /选择 Tokyo Night 主题/ });
    fireEvent.click(tokyoCard);

    expect(useCuratedThemeStore.getState().activeThemeId).toBe('tokyo-night');
    expect(onThemeSelect).toHaveBeenCalledWith('tokyo-night');
  });

  it('resets theme to default when clicking default button', () => {
    useCuratedThemeStore.getState().setTheme('nord');
    render(<CuratedThemeMatrixPicker />);

    const resetBtn = screen.getByRole('button', { name: /恢复默认暗色模式/ });
    fireEvent.click(resetBtn);

    expect(useCuratedThemeStore.getState().activeThemeId).toBe('default-dark');
  });

  it('toggles system dark sync checkbox', () => {
    render(<CuratedThemeMatrixPicker />);
    const checkbox = screen.getByRole('checkbox', { name: /跟随系统深色/ }) as HTMLInputElement;

    expect(checkbox.checked).toBe(true);
    fireEvent.click(checkbox);
    expect(checkbox.checked).toBe(false);
    expect(useCuratedThemeStore.getState().syncWithSystemDark).toBe(false);
  });
});
