/** @vitest-environment jsdom */
/** A settings switch row as a screen-reader user meets it: the switch is named by the row title and described by the row text. */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import ConfigToggleItem from '../ConfigToggleItem';

const Icon = () => <svg aria-hidden="true" />;

afterEach(cleanup);

describe('ConfigToggleItem', () => {
  it('names the switch after the row title and describes it with the row description', () => {
    render(
      <ConfigToggleItem
        icon={Icon}
        title="Full duplex"
        description="Keep the microphone open while the reply is spoken"
        checked={false}
        onCheckedChange={vi.fn()}
      />,
    );

    const toggle = screen.getByRole('switch', { name: 'Full duplex' });
    expect(toggle).toHaveAccessibleDescription('Keep the microphone open while the reply is spoken');
  });

  it('reports the new state when the switch is used', () => {
    const onCheckedChange = vi.fn();
    render(
      <ConfigToggleItem
        icon={Icon}
        title="Full duplex"
        description="d"
        checked={false}
        onCheckedChange={onCheckedChange}
      />,
    );

    fireEvent.click(screen.getByRole('switch', { name: 'Full duplex' }));

    expect(onCheckedChange).toHaveBeenCalledExactlyOnceWith(true);
  });

  it('gives each row on one page its own name', () => {
    render(
      <>
        <ConfigToggleItem icon={Icon} title="Full duplex" description="a" checked onCheckedChange={vi.fn()} />
        <ConfigToggleItem icon={Icon} title="Agent bridge" description="b" checked={false} onCheckedChange={vi.fn()} />
      </>,
    );

    expect(screen.getByRole('switch', { name: 'Full duplex' })).toBeChecked();
    expect(screen.getByRole('switch', { name: 'Agent bridge' })).not.toBeChecked();
  });
});
