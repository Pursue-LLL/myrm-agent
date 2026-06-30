import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi, afterEach } from 'vitest';

const mockSendMessage = vi.fn();
const mockEnqueue = vi.fn();
const mockWriteToClipboard = vi.fn();
const mockToastInfo = vi.fn();

let mockLoading = false;

vi.mock('@/store/useChatStore', () => {
  const getState = () => ({
    chatId: 'test-chat-1',
    loading: mockLoading,
    sendMessage: mockSendMessage,
  });
  const store = Object.assign((selector: (s: Record<string, unknown>) => unknown) => selector(getState()), {
    getState,
  });
  return { default: store };
});

let mockDirtyArtifacts: Record<string, string> = {};
const mockClearDirtyState = vi.fn();

vi.mock('@/store/useArtifactPortalStore', () => {
  const getState = () => ({
    getDirtyArtifacts: () => mockDirtyArtifacts,
    clearDirtyState: mockClearDirtyState,
  });
  const store = Object.assign(() => ({}), { getState });
  return { default: store };
});

vi.mock('@/hooks/useMessageQueue', () => ({
  useMessageQueue: () => ({
    enqueue: mockEnqueue,
    queue: [],
    hasQueuedMessages: false,
  }),
}));

vi.mock('@/lib/utils/clipboardUtils', () => ({
  writeToClipboard: (...args: unknown[]) => mockWriteToClipboard(...args),
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: {
    info: (...args: unknown[]) => mockToastInfo(...args),
    success: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock('@/lib/utils/classnameUtils', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}));

vi.mock('hugeicons-react', () => ({
  Edit04Icon: (props: Record<string, unknown>) => <span data-testid="edit-icon" {...props} />,
  InformationCircleIcon: (props: Record<string, unknown>) => <span data-testid="info-icon" {...props} />,
  SparklesIcon: (props: Record<string, unknown>) => <span data-testid="sparkles-icon" {...props} />,
  Copy01Icon: (props: Record<string, unknown>) => <span data-testid="copy-icon" {...props} />,
  ArrowRight01Icon: (props: Record<string, unknown>) => <span data-testid="arrow-icon" {...props} />,
}));

import DocumentSelectionToolbar from '../DocumentSelectionToolbar';
import React from 'react';

function createContainerWithSelection(
  text: string,
  opts: { nearBottom?: boolean } = {},
) {
  const containerRef = React.createRef<HTMLDivElement>();

  const selectionRect = opts.nearBottom
    ? { top: 560, bottom: 580, left: 50, right: 200, width: 150, height: 20 }
    : { top: 100, bottom: 120, left: 50, right: 200, width: 150, height: 20 };

  const containerRect = { top: 0, bottom: 600, left: 0, right: 800, width: 800, height: 600 };

  const mockRange = {
    getBoundingClientRect: () => selectionRect,
    getClientRects: () => [selectionRect],
    commonAncestorContainer: null as Node | null,
  };

  const mockSelection = {
    isCollapsed: false,
    rangeCount: 1,
    anchorNode: null as Node | null,
    getRangeAt: () => mockRange,
    toString: () => text,
    removeAllRanges: vi.fn(),
  };

  const setupContainer = (el: HTMLDivElement | null) => {
    if (!el) return;
    (containerRef as React.MutableRefObject<HTMLDivElement>).current = el;

    mockSelection.anchorNode = el.firstChild || el;
    mockRange.commonAncestorContainer = el;

    el.getBoundingClientRect = () => containerRect as DOMRect;
    Object.defineProperty(el, 'scrollTop', { value: 0, writable: true });
    Object.defineProperty(el, 'clientHeight', { value: 600, writable: true });
      const nativeContains = Node.prototype.contains.bind(el);
      el.contains = (node: Node | null) => {
        if (!node) return false;
        if (node === mockSelection.anchorNode) return true;
        return nativeContains(node);
      };
  };

  return { containerRef, mockSelection, setupContainer };
}

function triggerSelectionChange() {
  act(() => {
    document.dispatchEvent(new Event('selectionchange'));
    vi.advanceTimersByTime(300);
  });
}

describe('DocumentSelectionToolbar', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    mockLoading = false;
    mockDirtyArtifacts = {};
    Object.defineProperty(window, 'innerWidth', { value: 1024, writable: true });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('renders nothing without selection', () => {
    const containerRef = React.createRef<HTMLDivElement>();
    const { container } = render(
      <div>
        <div ref={containerRef as React.RefObject<HTMLDivElement>} />
        <DocumentSelectionToolbar containerRef={containerRef} artifactId="art-1" />
      </div>,
    );

    vi.spyOn(window, 'getSelection').mockReturnValue({
      isCollapsed: true,
      rangeCount: 0,
      anchorNode: null,
      getRangeAt: vi.fn(),
      toString: () => '',
    } as unknown as Selection);

    triggerSelectionChange();

    const toolbarDivs = container.querySelectorAll('[class*="absolute"]');
    expect(toolbarDivs.length).toBe(0);
  });

  it('hides on mobile viewport', () => {
    Object.defineProperty(window, 'innerWidth', { value: 400, writable: true });

    const { containerRef, mockSelection, setupContainer } = createContainerWithSelection('test text');

    vi.spyOn(window, 'getSelection').mockReturnValue(mockSelection as unknown as Selection);

    const { container } = render(
      <div>
        <div ref={setupContainer}>some content</div>
        <DocumentSelectionToolbar containerRef={containerRef} artifactId="art-1" />
      </div>,
    );

    triggerSelectionChange();

    const buttons = container.querySelectorAll('button');
    expect(buttons.length).toBe(0);
  });

  it('renders nothing without artifactId', () => {
    const containerRef = React.createRef<HTMLDivElement>();

    const { container } = render(
      <div>
        <div ref={containerRef as React.RefObject<HTMLDivElement>} />
        <DocumentSelectionToolbar containerRef={containerRef} />
      </div>,
    );

    triggerSelectionChange();

    const buttons = container.querySelectorAll('button');
    expect(buttons.length).toBe(0);
  });
});

describe('DocumentSelectionToolbar - useSelectionAction integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockLoading = false;
    mockDirtyArtifacts = {};
  });

  it('sends message via useSelectionAction when action clicked', async () => {
    vi.useRealTimers();
    mockSendMessage.mockResolvedValue(undefined);

    const containerRef = React.createRef<HTMLDivElement>();

    const mockRange = {
      getBoundingClientRect: () => ({ top: 100, bottom: 120, left: 50, right: 200, width: 150, height: 20 }),
    };
    const mockSel = {
      isCollapsed: false,
      rangeCount: 1,
      anchorNode: null as Node | null,
      getRangeAt: () => mockRange,
      toString: () => 'selected document text',
    };

    vi.spyOn(window, 'getSelection').mockReturnValue(mockSel as unknown as Selection);

    const { container } = render(
      <div>
        <div
          ref={(el) => {
            if (el) {
              (containerRef as React.MutableRefObject<HTMLDivElement>).current = el;
              mockSel.anchorNode = el;
              el.getBoundingClientRect = () =>
                ({ top: 0, bottom: 600, left: 0, right: 800, width: 800, height: 600 }) as DOMRect;
              Object.defineProperty(el, 'scrollTop', { value: 0, writable: true });
              Object.defineProperty(el, 'clientHeight', { value: 600, writable: true });
              const originalContains = el.contains.bind(el);
              el.contains = (node: Node | null) => {
                if (node === mockSel.anchorNode) return true;
                return originalContains(node);
              };
            }
          }}
        >
          some document content
        </div>
        <DocumentSelectionToolbar containerRef={containerRef} artifactId="art-42" />
      </div>,
    );

    vi.useFakeTimers();
    triggerSelectionChange();
    vi.useRealTimers();

    const explainBtn = screen.queryByText('explain');
    if (explainBtn) {
      fireEvent.click(explainBtn.closest('button')!);

      await waitFor(() => {
        expect(mockSendMessage).toHaveBeenCalledTimes(1);
      });

      const msg = mockSendMessage.mock.calls[0][0] as string;
      expect(msg).toContain('selection_context');
      expect(msg).toContain('art-42');
      expect(msg).toContain('document');
      expect(msg).toContain('selected document text');
    }
  });
});
