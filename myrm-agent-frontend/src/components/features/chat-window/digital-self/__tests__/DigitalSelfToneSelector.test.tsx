import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import DigitalSelfToneSelector from '../DigitalSelfToneSelector';

describe('DigitalSelfToneSelector', () => {
  it('renders all four corporate tone options', () => {
    const onSelectTone = vi.fn();
    render(<DigitalSelfToneSelector currentTone="formal" onSelectTone={onSelectTone} />);

    expect(screen.getByText('语气风格')).toBeDefined();
    expect(screen.getByTestId('tone-btn-formal')).toBeDefined();
    expect(screen.getByTestId('tone-btn-semi-formal')).toBeDefined();
    expect(screen.getByTestId('tone-btn-friendly')).toBeDefined();
    expect(screen.getByTestId('tone-btn-concise')).toBeDefined();
  });

  it('triggers onSelectTone when an option is clicked', () => {
    const onSelectTone = vi.fn();
    render(<DigitalSelfToneSelector currentTone="formal" onSelectTone={onSelectTone} />);

    const friendlyBtn = screen.getByTestId('tone-btn-friendly');
    fireEvent.click(friendlyBtn);

    expect(onSelectTone).toHaveBeenCalledWith('friendly');
  });

  it('does not trigger onSelectTone when disabled is true', () => {
    const onSelectTone = vi.fn();
    render(<DigitalSelfToneSelector currentTone="formal" onSelectTone={onSelectTone} disabled={true} />);

    const conciseBtn = screen.getByTestId('tone-btn-concise');
    fireEvent.click(conciseBtn);

    expect(onSelectTone).not.toHaveBeenCalled();
  });
});
