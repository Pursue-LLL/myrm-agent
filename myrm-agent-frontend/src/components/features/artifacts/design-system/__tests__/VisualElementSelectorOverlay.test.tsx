import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import { VisualElementSelectorOverlay } from '../VisualElementSelectorOverlay';
import { useVisualArtifactStudioStore } from '../useVisualArtifactStudioStore';

describe('VisualElementSelectorOverlay', () => {
  beforeEach(() => {
    act(() => {
      useVisualArtifactStudioStore.getState().resetStudioState();
    });
  });

  it('当 isInspectMode 为 false 时不渲染任何内容', () => {
    const { container } = render(<VisualElementSelectorOverlay />);
    expect(container.firstChild).toBeNull();
  });

  it('开启审查模式后渲染蒙层与可点击审查热区', () => {
    act(() => {
      useVisualArtifactStudioStore.getState().toggleInspectMode(true);
    });

    render(<VisualElementSelectorOverlay />);

    expect(
      screen.getByRole('region', { name: '所见即所得元素审查框选蒙层' })
    ).toBeInTheDocument();
    expect(
      screen.getByText('元素审查模式开启 (悬停并点击框选)')
    ).toBeInTheDocument();

    const titleHotspot = screen.getByRole('button', {
      name: '审查元素: .hero-container > h1.title',
    });
    expect(titleHotspot).toBeInTheDocument();
  });

  it('点击热区能够选中元素并高亮盒模型与尺寸药丸', () => {
    act(() => {
      useVisualArtifactStudioStore.getState().toggleInspectMode(true);
    });

    render(<VisualElementSelectorOverlay />);

    const ctaHotspot = screen.getByRole('button', {
      name: '审查元素: .hero-container > button.cta-button',
    });

    act(() => {
      fireEvent.click(ctaHotspot);
    });

    expect(
      useVisualArtifactStudioStore.getState().selectedElement?.selectorPath
    ).toBe('.hero-container > button.cta-button');

    expect(screen.getByTestId('inspect-highlight-box')).toBeInTheDocument();
    expect(screen.getByText(/button • 140×40px/)).toBeInTheDocument();
  });

  it('点击退出按钮能够关闭审查模式', () => {
    act(() => {
      useVisualArtifactStudioStore.getState().toggleInspectMode(true);
    });

    render(<VisualElementSelectorOverlay />);

    const exitBtn = screen.getByRole('button', { name: '退出审查模式' });
    act(() => {
      fireEvent.click(exitBtn);
    });

    expect(useVisualArtifactStudioStore.getState().isInspectMode).toBe(false);
  });
});
