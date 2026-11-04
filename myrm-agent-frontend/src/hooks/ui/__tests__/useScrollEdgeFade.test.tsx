/**
 * [INPUT]
 * - @/hooks/ui/useScrollEdgeFade::{observeScrollEdges, useScrollEdgeFade} (POS: 横向滚动区的边缘渐隐标记)
 *
 * [OUTPUT]
 * Vitest: 只有确有内容被裁的一侧才被标记渐隐，并随滚动、尺寸与子节点变化同步，卸载后不再观察。
 *
 * [POS]
 * jsdom 没有布局，滚动几何用实例属性桩出；ResizeObserver 用可手动触发的替身，保证断言的是真实的订阅与清理。
 */

import { render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { observeScrollEdges, useScrollEdgeFade } from '../useScrollEdgeFade';

class FakeResizeObserver {
  static instances: FakeResizeObserver[] = [];
  readonly observed = new Set<Element>();

  constructor(private readonly callback: () => void) {
    FakeResizeObserver.instances.push(this);
  }

  observe(target: Element): void {
    this.observed.add(target);
  }

  disconnect(): void {
    this.observed.clear();
  }

  trigger(): void {
    this.callback();
  }
}

interface Geometry {
  scrollWidth: number;
  clientWidth: number;
  scrollLeft: number;
}

function defineGeometry(element: HTMLElement, geometry: Geometry): Geometry {
  for (const key of Object.keys(geometry) as (keyof Geometry)[]) {
    Object.defineProperty(element, key, {
      configurable: true,
      get: () => geometry[key],
    });
  }
  return geometry;
}

function buildStrip(geometry: Geometry, childCount = 2): { strip: HTMLDivElement; geometry: Geometry } {
  const strip = document.createElement('div');
  for (let index = 0; index < childCount; index += 1) {
    strip.appendChild(document.createElement('span'));
  }
  return { strip, geometry: defineGeometry(strip, geometry) };
}

const flags = (element: HTMLElement) => ({ start: element.dataset.fadeStart, end: element.dataset.fadeEnd });

describe('observeScrollEdges', () => {
  beforeEach(() => {
    FakeResizeObserver.instances = [];
    vi.stubGlobal('ResizeObserver', FakeResizeObserver);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('fades only the end edge while the strip sits at its left edge and overflows', () => {
    const { strip } = buildStrip({ scrollWidth: 600, clientWidth: 200, scrollLeft: 0 });
    observeScrollEdges(strip);
    expect(flags(strip)).toEqual({ start: 'false', end: 'true' });
  });

  it('fades both edges mid-scroll and only the start edge at the far end', () => {
    const { strip, geometry } = buildStrip({ scrollWidth: 600, clientWidth: 200, scrollLeft: 0 });
    observeScrollEdges(strip);

    geometry.scrollLeft = 100;
    strip.dispatchEvent(new Event('scroll'));
    expect(flags(strip)).toEqual({ start: 'true', end: 'true' });

    geometry.scrollLeft = 400;
    strip.dispatchEvent(new Event('scroll'));
    expect(flags(strip)).toEqual({ start: 'true', end: 'false' });
  });

  it('fades nothing when the content fits, including a one-pixel rounding gap', () => {
    const fits = buildStrip({ scrollWidth: 200, clientWidth: 200, scrollLeft: 0 });
    observeScrollEdges(fits.strip);
    expect(flags(fits.strip)).toEqual({ start: 'false', end: 'false' });

    const rounded = buildStrip({ scrollWidth: 201, clientWidth: 200, scrollLeft: 0 });
    observeScrollEdges(rounded.strip);
    expect(flags(rounded.strip)).toEqual({ start: 'false', end: 'false' });
  });

  it('re-evaluates when the layout resizes', () => {
    const { strip, geometry } = buildStrip({ scrollWidth: 200, clientWidth: 200, scrollLeft: 0 });
    observeScrollEdges(strip);
    expect(flags(strip).end).toBe('false');

    geometry.scrollWidth = 600;
    FakeResizeObserver.instances[0].trigger();
    expect(flags(strip).end).toBe('true');
  });

  it('observes the strip and every child, including children added later', async () => {
    const { strip } = buildStrip({ scrollWidth: 600, clientWidth: 200, scrollLeft: 0 });
    observeScrollEdges(strip);
    const observer = FakeResizeObserver.instances[0];
    expect(observer.observed.size).toBe(3);

    const added = document.createElement('button');
    strip.appendChild(added);
    await vi.waitFor(() => expect(observer.observed.has(added)).toBe(true));
    expect(observer.observed.size).toBe(4);
  });

  it('stops reacting and releases its observers once stopped', () => {
    const { strip, geometry } = buildStrip({ scrollWidth: 600, clientWidth: 200, scrollLeft: 0 });
    const stop = observeScrollEdges(strip);
    stop();

    geometry.scrollLeft = 100;
    strip.dispatchEvent(new Event('scroll'));
    expect(flags(strip)).toEqual({ start: 'false', end: 'true' });
    expect(FakeResizeObserver.instances[0].observed.size).toBe(0);
  });

  it('still tracks scrolling where ResizeObserver does not exist', () => {
    vi.stubGlobal('ResizeObserver', undefined);
    const { strip, geometry } = buildStrip({ scrollWidth: 600, clientWidth: 200, scrollLeft: 0 });
    observeScrollEdges(strip);

    geometry.scrollLeft = 100;
    strip.dispatchEvent(new Event('scroll'));
    expect(flags(strip)).toEqual({ start: 'true', end: 'true' });
  });
});

describe('useScrollEdgeFade', () => {
  beforeEach(() => {
    FakeResizeObserver.instances = [];
    vi.stubGlobal('ResizeObserver', FakeResizeObserver);
    Object.defineProperty(HTMLElement.prototype, 'scrollWidth', { configurable: true, get: () => 600 });
    Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, get: () => 200 });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    delete (HTMLElement.prototype as { scrollWidth?: number }).scrollWidth;
    delete (HTMLElement.prototype as { clientWidth?: number }).clientWidth;
  });

  function Strip() {
    const fadeRef = useScrollEdgeFade<HTMLDivElement>();
    return (
      <div ref={fadeRef} data-testid="strip">
        <span>a</span>
      </div>
    );
  }

  it('marks the mounted element and releases the observer on unmount', () => {
    const { getByTestId, unmount } = render(<Strip />);
    expect(flags(getByTestId('strip'))).toEqual({ start: 'false', end: 'true' });

    const observer = FakeResizeObserver.instances.at(-1);
    expect(observer?.observed.size).toBe(2);
    unmount();
    expect(observer?.observed.size).toBe(0);
  });
});
