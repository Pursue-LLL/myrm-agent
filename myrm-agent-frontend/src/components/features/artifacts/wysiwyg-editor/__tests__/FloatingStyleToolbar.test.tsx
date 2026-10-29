import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { FloatingStyleToolbar } from '../FloatingStyleToolbar';
import { useWysiwygEditorStore } from '../useWysiwygEditorStore';
import { SelectedDomElementInfo } from '../wysiwygEditorTypes';

describe('FloatingStyleToolbar', () => {
  beforeEach(() => {
    act(() => {
      useWysiwygEditorStore.getState().reset();
    });
  });

  const sampleElement: SelectedDomElementInfo = {
    selector: 'h2.article-title',
    tagName: 'H2',
    textContent: '测试标题',
    styles: {},
  };

  it('在无选中元素时不渲染任何 DOM', () => {
    render(<FloatingStyleToolbar />);
    expect(
      screen.queryByTestId('floating-style-toolbar')
    ).not.toBeInTheDocument();
  });

  it('选定元素后正确呈现选择器、调色盘、字号阶梯与关闭按钮', () => {
    act(() => {
      useWysiwygEditorStore.getState().selectElement(sampleElement);
    });

    render(<FloatingStyleToolbar />);

    expect(
      screen.getByTestId('floating-style-toolbar')
    ).toBeInTheDocument();
    expect(screen.getByText('h2.article-title')).toBeInTheDocument();
    expect(screen.getByText('SM')).toBeInTheDocument();
    expect(screen.getByText('BASE')).toBeInTheDocument();
    expect(screen.getByText('LG')).toBeInTheDocument();
    expect(screen.getByText('XL')).toBeInTheDocument();
    expect(screen.getByLabelText('关闭样式面板')).toBeInTheDocument();
  });

  it('点击颜色按钮能够更新元素的前景色样式', () => {
    act(() => {
      useWysiwygEditorStore.getState().selectElement(sampleElement);
    });

    render(<FloatingStyleToolbar />);

    const colorBtn = screen.getByLabelText('文字颜色 #6366f1');
    act(() => {
      fireEvent.click(colorBtn);
    });

    expect(
      useWysiwygEditorStore.getState().selectedElement?.styles.color
    ).toBe('#6366f1');
  });

  it('点击字号按钮能够更新元素的 fontSize 规则', () => {
    act(() => {
      useWysiwygEditorStore.getState().selectElement(sampleElement);
    });

    render(<FloatingStyleToolbar />);

    const lgBtn = screen.getByText('LG');
    act(() => {
      fireEvent.click(lgBtn);
    });

    expect(
      useWysiwygEditorStore.getState().selectedElement?.styles.fontSize
    ).toBe('18px');
  });

  it('点击关闭面板按钮能够清除当前选中态', () => {
    act(() => {
      useWysiwygEditorStore.getState().selectElement(sampleElement);
    });

    render(<FloatingStyleToolbar />);

    const closeBtn = screen.getByLabelText('关闭样式面板');
    act(() => {
      fireEvent.click(closeBtn);
    });

    expect(useWysiwygEditorStore.getState().selectedElement).toBeNull();
    expect(
      screen.queryByTestId('floating-style-toolbar')
    ).not.toBeInTheDocument();
  });
});
