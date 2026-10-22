import React, { act } from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LivePrototypeCanvas } from '../LivePrototypeCanvas';
import { usePrototypeCanvasStore } from '../usePrototypeCanvasStore';

const mockTranslations = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => mockTranslations,
}));

describe('LivePrototypeCanvas', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    usePrototypeCanvasStore.getState().reset();
  });

  it('renders prototype canvas with toolbar, title, and default desktop frame', async () => {
    await act(async () => {
      render(
        <LivePrototypeCanvas
          content="<div class='dashboard'>Dashboard Prototype</div>"
          title="CRM Dashboard"
          filename="crm_intent.md"
        />
      );
      await Promise.resolve();
    });

    expect(screen.getByTestId('live-prototype-canvas-root')).toBeInTheDocument();
    expect(screen.getByTestId('prototype-canvas-toolbar')).toBeInTheDocument();
    expect(screen.getByText('crm_intent.md')).toBeInTheDocument();
    expect(screen.getByTestId('prototype-frame-desktop')).toBeInTheDocument();
  });

  it('switches viewport across desktop, tablet, and mobile', async () => {
    await act(async () => {
      render(
        <LivePrototypeCanvas
          content="<div>Canvas Content</div>"
        />
      );
      await Promise.resolve();
    });

    // Switch to tablet
    await act(async () => {
      fireEvent.click(screen.getByTestId('viewport-tablet-btn'));
      await Promise.resolve();
    });
    expect(usePrototypeCanvasStore.getState().viewport).toBe('tablet');
    expect(screen.getByTestId('prototype-frame-tablet')).toBeInTheDocument();

    // Switch to mobile
    await act(async () => {
      fireEvent.click(screen.getByTestId('viewport-mobile-btn'));
      await Promise.resolve();
    });
    expect(usePrototypeCanvasStore.getState().viewport).toBe('mobile');
    expect(screen.getByTestId('prototype-frame-mobile')).toBeInTheDocument();

    // Switch back to desktop
    await act(async () => {
      fireEvent.click(screen.getByTestId('viewport-desktop-btn'));
      await Promise.resolve();
    });
    expect(usePrototypeCanvasStore.getState().viewport).toBe('desktop');
    expect(screen.getByTestId('prototype-frame-desktop')).toBeInTheDocument();
  });

  it('toggles annotating mode and accepts element comment input', async () => {
    await act(async () => {
      render(
        <LivePrototypeCanvas
          content="<button class='save-btn'>Save</button>"
        />
      );
      await Promise.resolve();
    });

    const toggleBtn = screen.getByTestId('toggle-annotating-btn');
    await act(async () => {
      fireEvent.click(toggleBtn);
      await Promise.resolve();
    });
    expect(usePrototypeCanvasStore.getState().isAnnotating).toBe(true);

    // Simulate clicking an element inside the iframe sandbox
    await act(async () => {
      window.dispatchEvent(
        new MessageEvent('message', {
          data: {
            type: 'MYRM_PROTOTYPE_PICK',
            tag: 'button',
            selector: '.save-btn',
            rect: { x: 100, y: 200, width: 80, height: 36 },
          },
        })
      );
      await Promise.resolve();
    });

    // Annotation prompt bubble should appear
    expect(screen.getByTestId('annotation-bubble')).toBeInTheDocument();

    // Type comment and submit
    const textarea = screen.getByTestId('annotation-input');
    await act(async () => {
      fireEvent.change(textarea, { target: { value: '按钮增加加载微动效' } });
      await Promise.resolve();
    });

    const submitBtn = screen.getByTestId('submit-annotation-btn');
    await act(async () => {
      fireEvent.click(submitBtn);
      await Promise.resolve();
    });

    // Verify stored annotation
    const annotations = usePrototypeCanvasStore.getState().annotations;
    expect(annotations.length).toBe(1);
    expect(annotations[0].elementSelector).toBe('.save-btn');
    expect(annotations[0].comment).toBe('按钮增加加载微动效');
    expect(screen.queryByTestId('annotation-bubble')).toBeNull();
  });

  it('triggers engineering spec handoff when approve button is clicked', async () => {
    const onHandoffSpecMock = vi.fn();

    await act(async () => {
      render(
        <LivePrototypeCanvas
          content="# Intent: 实时行情看板"
          title="Market Hub"
          onHandoffSpec={onHandoffSpecMock}
        />
      );
      await Promise.resolve();
    });

    const handoffBtn = screen.getByTestId('handoff-spec-btn');
    await act(async () => {
      fireEvent.click(handoffBtn);
      await Promise.resolve();
    });

    expect(onHandoffSpecMock).toHaveBeenCalledTimes(1);
    const callArg = onHandoffSpecMock.mock.calls[0][0];
    expect(callArg.prototypeTitle).toBe('Market Hub');
    expect(callArg.generatedSpecMarkdown).toContain('Engineering Handoff Spec');
    expect(screen.getByText('specHandoffDone')).toBeInTheDocument();
  });

  it('opens annotations drawer and allows resolving / deleting annotations', async () => {
    // Pre-populate store with an annotation
    act(() => {
      usePrototypeCanvasStore.getState().addAnnotation({
        elementTag: 'div',
        elementSelector: '#header',
        comment: '导航栏固定在顶部',
      });
    });

    await act(async () => {
      render(
        <LivePrototypeCanvas
          content="<div>Header</div>"
        />
      );
      await Promise.resolve();
    });

    // Open drawer
    const openDrawerBtn = screen.getByTestId('toggle-annotations-drawer-btn');
    await act(async () => {
      fireEvent.click(openDrawerBtn);
      await Promise.resolve();
    });

    expect(screen.getByTestId('annotations-drawer')).toBeInTheDocument();
    expect(screen.getByText('导航栏固定在顶部')).toBeInTheDocument();

    const annotationId = usePrototypeCanvasStore.getState().annotations[0].id;

    // Toggle resolve
    const resolveBtn = screen.getByTestId(`resolve-btn-${annotationId}`);
    await act(async () => {
      fireEvent.click(resolveBtn);
      await Promise.resolve();
    });
    expect(usePrototypeCanvasStore.getState().annotations[0].resolved).toBe(true);

    // Delete
    const deleteBtn = screen.getByTestId(`delete-btn-${annotationId}`);
    await act(async () => {
      fireEvent.click(deleteBtn);
      await Promise.resolve();
    });
    expect(usePrototypeCanvasStore.getState().annotations.length).toBe(0);
  });
});
