/** @vitest-environment jsdom */
/**
 * [INPUT]
 * - @/components/features/settings/sections/system/ShortcutRecorder
 *
 * [OUTPUT]
 * - Test suite for the global shortcut recorder input
 *
 * [POS]
 * Pins the recording contract: focus starts recording with localized feedback, a chord is reported once
 * as a normalized accelerator, Backspace clears and Escape cancels without reporting.
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import ShortcutRecorder from '../ShortcutRecorder';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

describe('ShortcutRecorder', () => {
  it('shows the saved shortcut until focused, then the localized recording hint', () => {
    render(<ShortcutRecorder value="Alt+Space" onChange={vi.fn()} />);
    const input = screen.getByRole('textbox');
    expect(input).toHaveValue('Alt+Space');

    fireEvent.focus(input);

    expect(input).toHaveValue('shortcutRecording');
  });

  it('exposes the localized placeholder for an empty shortcut', () => {
    render(<ShortcutRecorder value="" onChange={vi.fn()} />);

    expect(screen.getByRole('textbox')).toHaveAttribute('placeholder', 'shortcutPlaceholder');
  });

  it('reports a modifier chord once as a normalized accelerator and stops recording', () => {
    const onChange = vi.fn();
    render(<ShortcutRecorder value="" onChange={onChange} />);
    const input = screen.getByRole('textbox');

    fireEvent.focus(input);
    fireEvent.keyDown(input, { key: 'k', code: 'KeyK', ctrlKey: true, shiftKey: true });

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith('Control+Shift+K');
    expect(input).not.toHaveValue('shortcutRecording');
  });

  it('ignores a bare modifier press while recording', () => {
    const onChange = vi.fn();
    render(<ShortcutRecorder value="" onChange={onChange} />);
    const input = screen.getByRole('textbox');

    fireEvent.focus(input);
    fireEvent.keyDown(input, { key: 'Shift', code: 'ShiftLeft', shiftKey: true });

    expect(onChange).not.toHaveBeenCalled();
    expect(input).toHaveValue('shortcutRecording');
  });

  it('clears the shortcut on Backspace and cancels on Escape', () => {
    const onChange = vi.fn();
    render(<ShortcutRecorder value="Alt+Space" onChange={onChange} />);
    const input = screen.getByRole('textbox');

    fireEvent.focus(input);
    fireEvent.keyDown(input, { key: 'Escape', code: 'Escape' });
    expect(onChange).not.toHaveBeenCalled();
    expect(input).toHaveValue('Alt+Space');

    fireEvent.focus(input);
    fireEvent.keyDown(input, { key: 'Backspace', code: 'Backspace' });
    expect(onChange).toHaveBeenCalledWith('');
  });
});
