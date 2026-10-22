import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserPreviewAnnotationOverlay } from '../BrowserPreviewAnnotationOverlay';
import type { BrowserAnnotationPin } from '../browserAnnotationTypes';

describe('BrowserPreviewAnnotationOverlay', () => {
  const mockPins: BrowserAnnotationPin[] = [
    {
      id: 'pin-1',
      index: 1,
      box: { x: 20, y: 30, width: 100, height: 40, viewportWidth: 1000, viewportHeight: 800 },
      comment: 'Header title alignment',
      createdAt: 1700000000000,
      domMetadata: {
        cssSelector: 'header > h1',
        tagName: 'h1',
        classList: [],
        sanitizedOuterHtml: '<h1>Title</h1>',
        innerText: 'Title',
        computedStyles: { fontSize: '24px' },
        subtreeBranch: 'header',
      },
    },
    {
      id: 'pin-2',
      index: 2,
      box: { x: 50, y: 200, width: 150, height: 80, viewportWidth: 1000, viewportHeight: 800 },
      comment: 'Sidebar nav item padding',
      createdAt: 1700000001000,
      domMetadata: {
        cssSelector: 'aside > nav',
        tagName: 'nav',
        classList: [],
        sanitizedOuterHtml: '<nav>Menu</nav>',
        innerText: 'Menu',
        computedStyles: { padding: '8px' },
        subtreeBranch: 'aside',
      },
    },
  ];

  it('renders annotate toggle button and switches mode', () => {
    const onToggleAnnotate = vi.fn();
    const onAddPin = vi.fn();
    const onUpdatePinComment = vi.fn();
    const onRemovePin = vi.fn();
    const onClearAllPins = vi.fn();
    const onExportToComposer = vi.fn();

    render(
      <BrowserPreviewAnnotationOverlay
        isAnnotating={false}
        onToggleAnnotate={onToggleAnnotate}
        pins={[]}
        onAddPin={onAddPin}
        onUpdatePinComment={onUpdatePinComment}
        onRemovePin={onRemovePin}
        onClearAllPins={onClearAllPins}
        onExportToComposer={onExportToComposer}
        viewportWidth={1000}
        viewportHeight={800}
      />,
    );

    const toggleBtn = screen.getByTestId('toggle-annotate-btn');
    expect(toggleBtn).toHaveTextContent('Annotate');

    fireEvent.click(toggleBtn);
    expect(onToggleAnnotate).toHaveBeenCalledWith(true);
  });

  it('displays active pins and subtree grouping info when annotating', () => {
    const onToggleAnnotate = vi.fn();
    const onAddPin = vi.fn();
    const onUpdatePinComment = vi.fn();
    const onRemovePin = vi.fn();
    const onClearAllPins = vi.fn();
    const onExportToComposer = vi.fn();

    render(
      <BrowserPreviewAnnotationOverlay
        isAnnotating={true}
        onToggleAnnotate={onToggleAnnotate}
        pins={mockPins}
        onAddPin={onAddPin}
        onUpdatePinComment={onUpdatePinComment}
        onRemovePin={onRemovePin}
        onClearAllPins={onClearAllPins}
        onExportToComposer={onExportToComposer}
        viewportWidth={1000}
        viewportHeight={800}
      />,
    );

    expect(screen.getByText('Annotating Mode')).toBeInTheDocument();
    expect(screen.getByText('2 subtrees')).toBeInTheDocument();
    expect(screen.getByTestId('annotation-pin-pin-1')).toHaveTextContent('1');
    expect(screen.getByTestId('annotation-pin-pin-2')).toHaveTextContent('2');
  });

  it('triggers onAddPin when user drags mouse across canvas', async () => {
    const onToggleAnnotate = vi.fn();
    const onAddPin = vi.fn();
    const onUpdatePinComment = vi.fn();
    const onRemovePin = vi.fn();
    const onClearAllPins = vi.fn();
    const onExportToComposer = vi.fn();

    render(
      <BrowserPreviewAnnotationOverlay
        isAnnotating={true}
        onToggleAnnotate={onToggleAnnotate}
        pins={[]}
        onAddPin={onAddPin}
        onUpdatePinComment={onUpdatePinComment}
        onRemovePin={onRemovePin}
        onClearAllPins={onClearAllPins}
        onExportToComposer={onExportToComposer}
        viewportWidth={1000}
        viewportHeight={800}
      />,
    );

    const overlay = screen.getByTestId('browser-annotation-overlay');

    // Simulate drag from (100, 100) to (250, 200)
    fireEvent.mouseDown(overlay, { clientX: 100, clientY: 100, button: 0 });
    fireEvent.mouseMove(overlay, { clientX: 250, clientY: 200 });
    fireEvent.mouseUp(overlay);

    await waitFor(() => {
      expect(onAddPin).toHaveBeenCalledTimes(1);
    });

    const callArg = onAddPin.mock.calls[0][0];
    expect(callArg.box.width).toBeGreaterThanOrEqual(16);
    expect(callArg.box.height).toBeGreaterThanOrEqual(16);
  });

  it('triggers onClearAllPins when clear button is clicked', () => {
    const onToggleAnnotate = vi.fn();
    const onAddPin = vi.fn();
    const onUpdatePinComment = vi.fn();
    const onRemovePin = vi.fn();
    const onClearAllPins = vi.fn();
    const onExportToComposer = vi.fn();

    render(
      <BrowserPreviewAnnotationOverlay
        isAnnotating={true}
        onToggleAnnotate={onToggleAnnotate}
        pins={mockPins}
        onAddPin={onAddPin}
        onUpdatePinComment={onUpdatePinComment}
        onRemovePin={onRemovePin}
        onClearAllPins={onClearAllPins}
        onExportToComposer={onExportToComposer}
        viewportWidth={1000}
        viewportHeight={800}
      />,
    );

    const clearBtn = screen.getByTestId('clear-pins-btn');
    fireEvent.click(clearBtn);

    expect(onClearAllPins).toHaveBeenCalledTimes(1);
  });

  it('formats structured markdown and triggers onExportToComposer', () => {
    const onToggleAnnotate = vi.fn();
    const onAddPin = vi.fn();
    const onUpdatePinComment = vi.fn();
    const onRemovePin = vi.fn();
    const onClearAllPins = vi.fn();
    const onExportToComposer = vi.fn();

    render(
      <BrowserPreviewAnnotationOverlay
        isAnnotating={true}
        onToggleAnnotate={onToggleAnnotate}
        pins={mockPins}
        onAddPin={onAddPin}
        onUpdatePinComment={onUpdatePinComment}
        onRemovePin={onRemovePin}
        onClearAllPins={onClearAllPins}
        onExportToComposer={onExportToComposer}
        viewportWidth={1000}
        viewportHeight={800}
        pageUrl="http://localhost:3000/dashboard"
        pageTitle="Admin Dashboard"
      />,
    );

    const exportBtn = screen.getByTestId('export-composer-btn');
    expect(exportBtn).toHaveTextContent('Add 2 comments');

    fireEvent.click(exportBtn);

    expect(onExportToComposer).toHaveBeenCalledTimes(1);
    const payload = onExportToComposer.mock.calls[0][0];
    expect(payload.totalPins).toBe(2);
    expect(payload.pageTitle).toBe('Admin Dashboard');
    expect(payload.formattedPrompt).toContain('## Browser In-App Annotation Feedback');
    expect(payload.formattedPrompt).toContain('header > h1');
    expect(payload.formattedPrompt).toContain('Header title alignment');
    expect(payload.formattedPrompt).toContain('aside > nav');
    expect(payload.formattedPrompt).toContain('Sidebar nav item padding');
  });
});
