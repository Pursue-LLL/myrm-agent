import React from 'react';
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { WidgetGeneratorModal } from '../WidgetGeneratorModal';
import { useWidgetBridgeStore } from '../useWidgetBridgeStore';

describe('WidgetGeneratorModal', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useWidgetBridgeStore.getState().resetWidget();
    useWidgetBridgeStore.setState({ isGeneratorModalOpen: true });
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({
        code: 0,
        data: {
          snippet: '<script src="http://localhost:3000/widget/loader.js" data-chat-id="chat_test_123"></script>',
        },
      }),
    } as unknown as Response);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders nothing when isOpen is false', () => {
    const { container } = render(
      <WidgetGeneratorModal chatId="chat_test_123" isOpen={false} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders dialog, headings, and mode options when isOpen is true', async () => {
    render(<WidgetGeneratorModal chatId="chat_test_123" isOpen={true} />);

    expect(screen.getByRole('dialog')).toBeDefined();
    expect(screen.getByText('generatorTitle')).toBeDefined();
    expect(screen.getByText('modeBubble')).toBeDefined();
    expect(screen.getByText('modeDrawer')).toBeDefined();
    expect(screen.getByText('modeInline')).toBeDefined();
  });

  it('switches display mode upon clicking mode card', async () => {
    render(<WidgetGeneratorModal chatId="chat_test_123" isOpen={true} />);

    const drawerBtn = screen.getByText('modeDrawer');
    fireEvent.click(drawerBtn);

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalled();
    });
  });

  it('copies generated snippet to clipboard', async () => {
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    render(<WidgetGeneratorModal chatId="chat_test_123" isOpen={true} />);

    const copyBtn = screen.getByLabelText('copySnippet');
    await waitFor(() => {
      expect(copyBtn).not.toBeDisabled();
    });

    fireEvent.click(copyBtn);

    expect(writeTextMock).toHaveBeenCalledWith(
      expect.stringContaining('data-chat-id="chat_test_123"')
    );
  });

  it('handles close callback on close button click', () => {
    const onClose = vi.fn();
    render(<WidgetGeneratorModal chatId="chat_test_123" isOpen={true} onClose={onClose} />);

    const closeBtn = screen.getByLabelText('close');
    fireEvent.click(closeBtn);

    expect(onClose).toHaveBeenCalled();
    expect(useWidgetBridgeStore.getState().isGeneratorModalOpen).toBe(false);
  });
});
