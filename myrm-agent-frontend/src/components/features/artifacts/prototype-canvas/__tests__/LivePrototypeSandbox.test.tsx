import React, { act } from 'react';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LivePrototypeSandbox } from '../LivePrototypeSandbox';

describe('LivePrototypeSandbox', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders sandboxed iframe with strict sandbox policy and no allow-same-origin', async () => {
    const { container } = render(
      <LivePrototypeSandbox
        content="<div class='card'>Prototype Card</div>"
        viewport="desktop"
        isAnnotating={false}
      />
    );
    await act(async () => {
      await Promise.resolve();
    });

    const iframe = container.querySelector('iframe');
    expect(iframe).not.toBeNull();
    expect(iframe?.getAttribute('sandbox')).toBe('allow-scripts allow-forms');
    expect(iframe?.getAttribute('sandbox')).not.toContain('allow-same-origin');
    expect(screen.getByTestId('prototype-frame-desktop')).toBeInTheDocument();
  });

  it('switches viewport frame container across tablet and mobile modes', async () => {
    const { rerender } = render(
      <LivePrototypeSandbox
        content="<button>Click</button>"
        viewport="tablet"
        isAnnotating={false}
      />
    );

    expect(screen.getByTestId('prototype-frame-tablet')).toBeInTheDocument();
    expect(screen.queryByTestId('prototype-frame-desktop')).toBeNull();

    rerender(
      <LivePrototypeSandbox
        content="<button>Click</button>"
        viewport="mobile"
        isAnnotating={false}
      />
    );

    expect(screen.getByTestId('prototype-frame-mobile')).toBeInTheDocument();
    expect(screen.queryByTestId('prototype-frame-tablet')).toBeNull();
  });

  it('dispatches onElementSelect when receiving MYRM_PROTOTYPE_PICK postMessage from sandbox', async () => {
    const onElementSelectMock = vi.fn();

    await act(async () => {
      render(
        <LivePrototypeSandbox
          content="<button class='submit-btn'>Submit</button>"
          viewport="desktop"
          isAnnotating={true}
          onElementSelect={onElementSelectMock}
        />
      );
      await Promise.resolve();
    });

    // Simulate postMessage dispatched from sandboxed iframe
    await act(async () => {
      window.dispatchEvent(
        new MessageEvent('message', {
          data: {
            type: 'MYRM_PROTOTYPE_PICK',
            tag: 'button',
            selector: '.submit-btn',
            rect: { x: 50, y: 100, width: 80, height: 32 },
          },
        })
      );
      await Promise.resolve();
    });

    expect(onElementSelectMock).toHaveBeenCalledTimes(1);
    expect(onElementSelectMock).toHaveBeenCalledWith({
      tag: 'button',
      selector: '.submit-btn',
      rect: { x: 50, y: 100, width: 80, height: 32 },
    });
  });

  it('ignores irrelevant postMessage events gracefully', async () => {
    const onElementSelectMock = vi.fn();

    await act(async () => {
      render(
        <LivePrototypeSandbox
          content="<div>Empty</div>"
          viewport="desktop"
          isAnnotating={false}
          onElementSelect={onElementSelectMock}
        />
      );
      await Promise.resolve();
    });

    await act(async () => {
      window.dispatchEvent(
        new MessageEvent('message', {
          data: {
            type: 'SOME_OTHER_EVENT',
          },
        })
      );
      await Promise.resolve();
    });

    expect(onElementSelectMock).not.toHaveBeenCalled();
  });
});
