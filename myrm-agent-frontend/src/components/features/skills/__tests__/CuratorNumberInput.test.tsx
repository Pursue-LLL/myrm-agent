import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React, { useState } from 'react';
import CuratorNumberInput from '../CuratorNumberInput';

interface HarnessProps {
  initial: number;
  min: number;
  max?: number;
  step?: number;
  onCommit: (value: number) => void;
}

function Harness({ initial, min, max, step, onCommit }: HarnessProps) {
  const [value, setValue] = useState(initial);
  return (
    <CuratorNumberInput
      value={value}
      min={min}
      max={max}
      step={step}
      onCommit={(v) => {
        setValue(v);
        onCommit(v);
      }}
    />
  );
}

describe('CuratorNumberInput', () => {
  it('commits a typed value as soon as it is inside the range', async () => {
    const onCommit = vi.fn();
    const user = userEvent.setup();
    render(<Harness initial={30} min={1} onCommit={onCommit} />);
    const input = screen.getByRole('spinbutton');

    await user.clear(input);
    await user.type(input, '45');

    expect(onCommit).toHaveBeenLastCalledWith(45);
    expect(input).toHaveValue(45);
  });

  it('does not commit a value below the minimum while typing and clamps it on blur', async () => {
    const onCommit = vi.fn();
    const user = userEvent.setup();
    render(<Harness initial={50} min={5} onCommit={onCommit} />);
    const input = screen.getByRole('spinbutton');

    await user.clear(input);
    await user.type(input, '3');
    expect(onCommit).not.toHaveBeenCalled();

    await user.tab();
    expect(onCommit).toHaveBeenCalledTimes(1);
    expect(onCommit).toHaveBeenCalledWith(5);
    expect(input).toHaveValue(5);
  });

  it('clamps a value above the maximum on blur', async () => {
    const onCommit = vi.fn();
    const user = userEvent.setup();
    render(<Harness initial={3} min={2} max={10} onCommit={onCommit} />);
    const input = screen.getByRole('spinbutton');

    await user.clear(input);
    await user.type(input, '99');
    expect(onCommit).not.toHaveBeenCalledWith(99);

    await user.tab();
    expect(onCommit).toHaveBeenLastCalledWith(10);
    expect(input).toHaveValue(10);
  });

  it('rounds a fractional value of an integer field on blur', async () => {
    const onCommit = vi.fn();
    const user = userEvent.setup();
    render(<Harness initial={30} min={1} onCommit={onCommit} />);
    const input = screen.getByRole('spinbutton');

    await user.clear(input);
    await user.type(input, '7.6');
    expect(onCommit).not.toHaveBeenCalledWith(7.6);

    await user.tab();
    expect(onCommit).toHaveBeenLastCalledWith(8);
    expect(input).toHaveValue(8);
  });

  it('reverts an emptied field to the last committed value instead of committing zero', async () => {
    const onCommit = vi.fn();
    const user = userEvent.setup();
    render(<Harness initial={30} min={0} onCommit={onCommit} />);
    const input = screen.getByRole('spinbutton');

    await user.clear(input);
    await user.tab();

    expect(onCommit).not.toHaveBeenCalled();
    expect(input).toHaveValue(30);
  });

  it('keeps decimals for a fractional step and clamps them into the range', async () => {
    const onCommit = vi.fn();
    const user = userEvent.setup();
    render(<Harness initial={0.75} min={0.5} max={0.95} step={0.05} onCommit={onCommit} />);
    const input = screen.getByRole('spinbutton');

    await user.clear(input);
    await user.type(input, '0.7');
    expect(onCommit).toHaveBeenLastCalledWith(0.7);

    await user.clear(input);
    await user.type(input, '2');
    await user.tab();
    expect(onCommit).toHaveBeenLastCalledWith(0.95);
    expect(input).toHaveValue(0.95);
  });

  it('follows a value changed from outside', () => {
    const onCommit = vi.fn();
    const { rerender } = render(<CuratorNumberInput value={30} min={1} onCommit={onCommit} />);

    rerender(<CuratorNumberInput value={60} min={1} onCommit={onCommit} />);

    expect(screen.getByRole('spinbutton')).toHaveValue(60);
  });
});
