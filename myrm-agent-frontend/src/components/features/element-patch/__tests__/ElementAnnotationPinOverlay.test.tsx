import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ElementAnnotationPinOverlay } from '../ElementAnnotationPinOverlay';
import { useElementPatchStore } from '../useElementPatchStore';
import { ElementAnnotationItem } from '../elementPatchTypes';

describe('ElementAnnotationPinOverlay', () => {
  beforeEach(() => {
    useElementPatchStore.getState().reset();
  });

  it('renders nothing when no annotations exist', () => {
    const { container } = render(<ElementAnnotationPinOverlay />);
    expect(container.firstChild).toBeNull();
  });

  it('renders annotation pins with positioning and sequence index', () => {
    const annotations: ElementAnnotationItem[] = [
      {
        id: 'ann-1',
        artifactId: 'art-01',
        selector: '#hero-title',
        elementTagName: 'h1',
        boundingBox: { x: 50, y: 100, width: 200, height: 40 },
        instruction: '字号增大为 32px',
        status: 'pending',
        createdAt: Date.now(),
      },
    ];

    render(<ElementAnnotationPinOverlay annotations={annotations} />);

    expect(screen.getByTestId('element-annotation-pin-overlay')).toBeInTheDocument();
    expect(screen.getByTestId('annotation-pin-ann-1')).toBeInTheDocument();
    expect(screen.getByText('1')).toBeInTheDocument();
  });

  it('renders green check badge when status is resolved', () => {
    const annotations: ElementAnnotationItem[] = [
      {
        id: 'ann-resolved',
        artifactId: 'art-01',
        selector: '#cta-btn',
        elementTagName: 'button',
        boundingBox: { x: 80, y: 150, width: 120, height: 44 },
        instruction: '圆角改 8px',
        status: 'resolved',
        createdAt: Date.now(),
        resolvedAt: Date.now(),
      },
    ];

    render(<ElementAnnotationPinOverlay annotations={annotations} />);
    const pin = screen.getByTestId('annotation-pin-ann-resolved');
    expect(pin).toHaveClass('border-emerald-500/40');
    expect(screen.queryByText('1')).toBeNull(); // 已变为 Check 图标
  });

  it('handles pin click to select annotation and open drawer', () => {
    const annotations: ElementAnnotationItem[] = [
      {
        id: 'ann-click',
        artifactId: 'art-01',
        selector: '#nav-link',
        elementTagName: 'a',
        boundingBox: { x: 10, y: 10, width: 60, height: 20 },
        instruction: '间距加大',
        status: 'pending',
        createdAt: Date.now(),
      },
    ];

    render(<ElementAnnotationPinOverlay annotations={annotations} />);

    const pinBtn = screen.getByRole('button', {
      name: /查看第 1 处元素批注/i,
    });
    fireEvent.click(pinBtn);

    expect(useElementPatchStore.getState().selectedAnnotationId).toBe('ann-click');
    expect(useElementPatchStore.getState().isDrawerOpen).toBe(true);
  });
});
