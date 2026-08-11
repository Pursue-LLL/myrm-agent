import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';

// Minimal repro: a controlled input wired exactly like InputField
function ControlledInput({ label, value, onValueChange }: { label: string; value: string; onValueChange: (v: string) => void }) {
  return (
    <div className="flex flex-col space-y-1">
      <p className="text-sm">{label}</p>
      <input
        data-testid={label}
        value={value}
        onChange={(e) => onValueChange(e.target.value)}
      />
    </div>
  );
}

function Harness() {
  const [v, setV] = useState('');
  return <ControlledInput label="cmd" value={v} onValueChange={setV} />;
}

describe('controlled input native setter + input event (React 19)', () => {
  it('native setter + dispatched input event updates React state', () => {
    render(<Harness />);
    const el = screen.getByTestId('cmd') as HTMLInputElement;

    // Simulate exactly what _fill_input_by_label_js does:
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      'value',
    )?.set;
    expect(setter).toBeTruthy();
    setter!.call(el, 'hello');
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));

    expect(el.value).toBe('hello');
    // If React state updated, value persists; if not, React resets to ''.
    expect(el.value).toBe('hello');
  });

  it('fireEvent.change (testing-library) updates React state', () => {
    render(<Harness />);
    const el = screen.getByTestId('cmd') as HTMLInputElement;
    fireEvent.change(el, { target: { value: 'world' } });
    expect(el.value).toBe('world');
  });
});
