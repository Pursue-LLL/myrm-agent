/** @vitest-environment jsdom */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import useResearchStore from '@/store/useResearchStore';
import ResearchLayout from '../ResearchLayout';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

// The chat and the output panel load through next/dynamic; stubs keep this suite about the layout alone.
vi.mock('next/dynamic', () => ({
  default: (loader: () => Promise<unknown>) => {
    const testId = String(loader).includes('ChatWindow') ? 'chat-window' : 'output-panel';
    return () => <div data-testid={testId} />;
  },
}));
vi.mock('../ResourcePoolPanel', () => ({ default: () => <div data-testid="resource-pool" /> }));
vi.mock('../useResearchSync', () => ({ useResearchSync: vi.fn() }));

const pane = (name: 'resources' | 'chat' | 'output') => screen.getByRole('region', { name });
const paneRow = () => screen.getByTestId('resource-pool').closest<HTMLElement>('[style]');
const cssVar = (name: string) => paneRow()?.style.getPropertyValue(name);

function dragFromTo(handle: Element, fromX: number, toX: number) {
  fireEvent.pointerDown(handle, { clientX: fromX, pointerId: 1 });
  fireEvent.pointerMove(handle, { clientX: toX, pointerId: 1 });
  fireEvent.pointerUp(handle, { pointerId: 1 });
}

describe('ResearchLayout', () => {
  beforeEach(() => {
    act(() => useResearchStore.getState().reset());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('keeps all three panes mounted and shows only the active tab below the wide breakpoint', () => {
    render(<ResearchLayout />);

    expect(screen.getByTestId('resource-pool')).toBeInTheDocument();
    expect(screen.getByTestId('chat-window')).toBeInTheDocument();
    expect(screen.getByTestId('output-panel')).toBeInTheDocument();
    expect(pane('resources')).toHaveClass('block');
    expect(pane('chat')).toHaveClass('hidden');
    expect(pane('output')).toHaveClass('hidden');
  });

  it('switches the visible pane with the tabs without unmounting the others', () => {
    render(<ResearchLayout />);

    fireEvent.mouseDown(screen.getByRole('tab', { name: 'chat' }), { button: 0 });

    expect(useResearchStore.getState().activeTab).toBe('chat');
    expect(pane('chat')).toHaveClass('block');
    expect(pane('resources')).toHaveClass('hidden');
    expect(screen.getByTestId('resource-pool')).toBeInTheDocument();
  });

  it('points each tab at the pane it reveals', () => {
    render(<ResearchLayout />);

    for (const tab of screen.getAllByRole('tab')) {
      const target = document.getElementById(tab.getAttribute('aria-controls') ?? '');
      expect(target).toHaveAccessibleName(tab.textContent ?? '');
    }
  });

  it.each(['resources', 'chat', 'output'] as const)(
    'contains the layout of the %s pane so its fixed-position descendants stay inside it',
    (name) => {
      render(<ResearchLayout />);

      expect(pane(name)).toHaveClass('contain-layout');
    },
  );

  describe('resizing', () => {
    const renderInRow = (rowWidth: number) => {
      // jsdom has no layout and no live pointers, so the row width is fixed and pointer capture is a no-op.
      vi.spyOn(Element.prototype, 'clientWidth', 'get').mockReturnValue(rowWidth);
      vi.spyOn(Element.prototype, 'setPointerCapture').mockImplementation(() => undefined);
      const { container } = render(<ResearchLayout />);
      const [leftHandle, rightHandle] = Array.from(container.querySelectorAll('.cursor-col-resize'));
      return { leftHandle, rightHandle };
    };

    it('starts from the default pane widths', () => {
      renderInRow(1600);

      expect(cssVar('--research-left')).toBe('300px');
      expect(cssVar('--research-right')).toBe('380px');
    });

    it('widens the resource pane by the drag distance', () => {
      const { leftHandle } = renderInRow(1600);

      dragFromTo(leftHandle, 300, 360);

      expect(cssVar('--research-left')).toBe('360px');
    });

    it('stops each side pane at its own maximum', () => {
      const { leftHandle, rightHandle } = renderInRow(2400);

      dragFromTo(leftHandle, 300, 900);
      dragFromTo(rightHandle, 2000, 1000);

      expect(cssVar('--research-left')).toBe('480px');
      expect(cssVar('--research-right')).toBe('600px');
    });

    it('grows the output pane when its handle is dragged towards the chat', () => {
      const { rightHandle } = renderInRow(1600);

      dragFromTo(rightHandle, 1200, 1150);

      expect(cssVar('--research-right')).toBe('430px');
    });

    it('never leaves the chat narrower than its minimum', () => {
      const { leftHandle } = renderInRow(1100);

      dragFromTo(leftHandle, 300, 500);

      // 1100 row - 380 output pane - 12 drag handles - 420 chat minimum.
      expect(cssVar('--research-left')).toBe('288px');
    });

    it('ignores pointer moves once the drag has ended', () => {
      const { leftHandle } = renderInRow(1600);

      dragFromTo(leftHandle, 300, 340);
      fireEvent.pointerMove(leftHandle, { clientX: 500, pointerId: 1 });

      expect(cssVar('--research-left')).toBe('340px');
    });
  });
});
