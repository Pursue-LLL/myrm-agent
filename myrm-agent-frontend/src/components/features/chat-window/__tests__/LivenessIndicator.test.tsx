import { fireEvent, render, screen } from '@testing-library/react';
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import LivenessIndicator from '../LivenessIndicator';

const hoisted = vi.hoisted(() => ({ state: 'idle' as string }));

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'en'));
vi.mock('@/hooks/shell/useLivenessState', () => ({ useLivenessState: () => ({ state: hoisted.state }) }));

// Radix Tooltip positions itself with a ResizeObserver, which jsdom does not have.
beforeAll(() => {
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
});

afterAll(() => {
  vi.unstubAllGlobals();
});

beforeEach(() => {
  hoisted.state = 'idle';
});

const dot = (label: string) => screen.getByText(label).parentElement as HTMLElement;

describe('LivenessIndicator', () => {
  it('is hidden while the agent is idle', () => {
    const { container } = render(<LivenessIndicator />);

    expect(container).toBeEmptyDOMElement();
  });

  it.each([
    ['busy', 'Running tasks…', 'bg-amber-500'],
    ['degraded', 'Service degraded', 'bg-red-400'],
    ['draining', 'Shutting down…', 'bg-orange-400'],
    ['offline', 'Backend offline', 'bg-red-600'],
  ])('shows %s as a coloured dot that also says "%s" to a screen reader', (state, label, color) => {
    hoisted.state = state;
    render(<LivenessIndicator />);

    expect(dot(label)).toHaveClass(color);
    expect(screen.getByText(label)).toHaveClass('sr-only');
  });

  it('pulses only while the agent is busy', () => {
    hoisted.state = 'busy';
    const busy = render(<LivenessIndicator />);
    expect(dot('Running tasks…')).toHaveClass('animate-pulse');
    busy.unmount();

    hoisted.state = 'offline';
    render(<LivenessIndicator />);

    expect(dot('Backend offline')).not.toHaveClass('animate-pulse');
  });

  it('spells the state out in a tooltip on focus', async () => {
    hoisted.state = 'degraded';
    render(<LivenessIndicator />);

    fireEvent.focus(dot('Service degraded'));

    const tooltip = await screen.findByRole('tooltip');
    expect(tooltip).toHaveTextContent('Service degraded');
    // The dot sits at the bottom of the composer, so the tooltip opens upwards.
    expect(tooltip).toHaveAttribute('data-side', 'top');
  });
});
