import { render, screen } from '@testing-library/react';
import { useRef, type ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ComposerClearanceSpacer } from '../ComposerClearanceSpacer';

class ResizeObserverStub {
  static instances: ResizeObserverStub[] = [];
  observed: Element[] = [];
  disconnect = vi.fn();

  constructor(readonly callback: ResizeObserverCallback) {
    ResizeObserverStub.instances.push(this);
  }

  observe(element: Element) {
    this.observed.push(element);
  }

  unobserve() {}
}

/** The message column of the chat: the filler first, then whatever the test puts after it. */
function Column({ children }: { children: ReactNode }) {
  const columnRef = useRef<HTMLDivElement>(null);
  return (
    <div ref={columnRef}>
      <ComposerClearanceSpacer columnRef={columnRef} className="min-h-40" />
      {children}
    </div>
  );
}

const dock = <div data-composer-dock data-testid="dock" style={{ bottom: '20px' }} />;

function setDockHeight(height: number) {
  vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(height);
}

describe('composer clearance filler', () => {
  beforeEach(() => {
    ResizeObserverStub.instances = [];
    vi.stubGlobal('ResizeObserver', ResizeObserverStub);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('is as tall as the composer plus its bottom offset and a margin', () => {
    setDockHeight(300);
    const { container } = render(<Column>{dock}</Column>);

    const spacer = container.firstElementChild?.firstElementChild as HTMLElement;
    expect(spacer.style.height).toBe('336px');
    expect(spacer).toHaveClass('min-h-40');
  });

  it('follows the composer when its size changes', () => {
    setDockHeight(300);
    const { container } = render(<Column>{dock}</Column>);
    const spacer = container.firstElementChild?.firstElementChild as HTMLElement;
    const [observer] = ResizeObserverStub.instances;
    expect(observer.observed).toEqual([screen.getByTestId('dock')]);

    setDockHeight(445.2);
    observer.callback([], observer as unknown as ResizeObserver);

    // 445.2 rounds up with the offset and margin: 445.2 + 20 + 16 = 481.2.
    expect(spacer.style.height).toBe('482px');
  });

  it('stops observing when the list unmounts', () => {
    setDockHeight(300);
    const { unmount } = render(<Column>{dock}</Column>);

    unmount();

    expect(ResizeObserverStub.instances[0].disconnect).toHaveBeenCalledTimes(1);
  });

  it('leaves the minimum height alone when there is no composer in the column', () => {
    const { container } = render(<Column>{null}</Column>);

    const spacer = container.firstElementChild?.firstElementChild as HTMLElement;
    expect(spacer.style.height).toBe('');
    expect(ResizeObserverStub.instances).toHaveLength(0);
  });

  it('ignores a composer that is not a direct child of the column', () => {
    setDockHeight(300);
    const { container } = render(
      <Column>
        <div>{dock}</div>
      </Column>,
    );

    const spacer = container.firstElementChild?.firstElementChild as HTMLElement;
    expect(spacer.style.height).toBe('');
    expect(ResizeObserverStub.instances).toHaveLength(0);
  });
});
