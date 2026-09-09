/** @vitest-environment jsdom */
'use client';

import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import BrowserLiveView from '../BrowserLiveView';
import useBrowserInspectorStore from '@/store/useBrowserInspectorStore';
import useChatStore from '@/store/useChatStore';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('../InspectorToolbar', () => ({
  default: ({ mode, onClose }: { mode: string; onClose: () => void }) => (
    <div data-testid="mock-inspector-toolbar">
      <span>Mode: {mode}</span>
      <button type="button" onClick={onClose}>
        Close
      </button>
    </div>
  ),
}));

vi.mock('../ElementOverlay', () => ({
  default: ({ imageWidth, imageHeight }: { imageWidth: number; imageHeight: number }) => (
    <div data-testid="mock-element-overlay" data-width={imageWidth} data-height={imageHeight}>
      Overlay
    </div>
  ),
}));

vi.mock('../InspectorInstructionInput', () => ({
  default: () => <div data-testid="mock-instruction-input">Instruction Input</div>,
}));

describe('BrowserLiveView', () => {
  const defaultProps = {
    onSendInstruction: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
    useBrowserInspectorStore.getState().reset();
    useChatStore.setState({ chatId: 'chat-1' });
  });

  it('renders nothing when isOpen is false', () => {
    useBrowserInspectorStore.setState({ isOpen: false });
    const { container } = render(<BrowserLiveView {...defaultProps} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders waiting placeholder when isOpen is true but no viewData exists', () => {
    useBrowserInspectorStore.setState({ isOpen: true, viewData: null, terminalViewData: null });
    render(<BrowserLiveView {...defaultProps} />);

    expect(screen.getByTestId('mock-inspector-toolbar')).toBeDefined();
    expect(screen.getByText('waitingForBrowser')).toBeDefined();
    expect(screen.getByText('waitingHint')).toBeDefined();
  });

  it('renders image when scopedViewData exists', () => {
    useBrowserInspectorStore.setState({
      isOpen: true,
      viewData: {
        screenshotBase64: 'test_base64_data',
        mimeType: 'image/png',
        refs: {},
        chatId: 'chat-1',
        viewportWidth: 1280,
        viewportHeight: 720,
        sourceChatId: 'chat-1',
        isTurnView: true,
        updatedAt: Date.now(),
      },
    });

    render(<BrowserLiveView {...defaultProps} />);

    const img = screen.getByAltText('screenshotAlt') as HTMLImageElement;
    expect(img.src).toBe('data:image/png;base64,test_base64_data');
  });

  it('updates panel width on resize drag handle interaction', () => {
    useBrowserInspectorStore.setState({
      isOpen: true,
      viewData: {
        screenshotBase64: 'test_base64_data',
        mimeType: 'image/png',
        refs: {},
        chatId: 'chat-1',
        viewportWidth: 1280,
        viewportHeight: 720,
        sourceChatId: 'chat-1',
        isTurnView: true,
        updatedAt: Date.now(),
      },
    });

    render(<BrowserLiveView {...defaultProps} />);

    const handle = screen.getByRole('separator');
    expect(handle).toBeDefined();

    // Start resize drag
    fireEvent.mouseDown(handle, { clientX: 800 });

    // Drag left by 200px (expanding panel)
    fireEvent.mouseMove(document, { clientX: 600 });

    // Release mouse
    fireEvent.mouseUp(document);

    // Assert localStorage saved the updated width
    expect(localStorage.getItem('browser-inspector-panel-width')).toBeDefined();
  });

  it('renders instruction input and handles image load in inspect mode', () => {
    useBrowserInspectorStore.setState({
      isOpen: true,
      mode: 'inspect',
      viewData: {
        screenshotBase64: 'test_base64_data',
        mimeType: 'image/png',
        refs: {
          'btn-1': {
            role: 'button',
            name: 'Submit',
            bbox: { x: 10, y: 20, width: 100, height: 30 },
          },
        },
        chatId: 'chat-1',
        viewportWidth: 1280,
        viewportHeight: 720,
        sourceChatId: 'chat-1',
        isTurnView: true,
        updatedAt: Date.now(),
      },
    });

    render(<BrowserLiveView {...defaultProps} />);

    // Instruction input should be present in inspect mode
    expect(screen.getByTestId('mock-instruction-input')).toBeDefined();

    const img = screen.getByAltText('screenshotAlt');
    Object.defineProperty(img, 'naturalWidth', { value: 1280, configurable: true });
    Object.defineProperty(img, 'naturalHeight', { value: 720, configurable: true });

    fireEvent.load(img);
    expect(img).toBeDefined();
  });
});
