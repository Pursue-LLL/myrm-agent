import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { InSituPropertyInspector } from '../InSituPropertyInspector';
import { useInsituAnnotationStore } from '../useInsituAnnotationStore';

describe('InSituPropertyInspector 组件单测', () => {
  beforeEach(() => {
    useInsituAnnotationStore.setState({
      stylePatches: [],
      inspectionTarget: {
        selector: '#hero-title',
        tagName: 'h1',
        boundingClientRect: { top: 50, left: 100, width: 300, height: 40 },
        currentStyles: {
          color: '#ffffff',
          backgroundColor: '#000000',
          fontSize: '24px',
          padding: '8px',
        },
        currentText: '新一代智能协同中枢',
      },
    });
  });

  it('当 inspectionTarget 为 null 时不渲染微调浮层', () => {
    useInsituAnnotationStore.setState({ inspectionTarget: null });
    const { container } = render(<InSituPropertyInspector />);

    expect(container.firstChild).toBeNull();
    expect(screen.queryByTestId('insitu-property-inspector')).not.toBeInTheDocument();
  });

  it('当 inspectionTarget 存在时完整渲染元素信息与属性微调表单', () => {
    render(<InSituPropertyInspector />);

    expect(screen.getByTestId('insitu-property-inspector')).toBeInTheDocument();
    expect(screen.getByText('就地属性微调')).toBeInTheDocument();
    expect(screen.getByText('h1')).toBeInTheDocument();
    expect(screen.getByDisplayValue('新一代智能协同中枢')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '应用补丁' })).toBeInTheDocument();
  });

  it('修改属性并点击「应用补丁」能将补丁写入 Store 并关闭浮层', () => {
    render(<InSituPropertyInspector />);

    const textInput = screen.getByDisplayValue('新一代智能协同中枢');
    fireEvent.change(textInput, { target: { value: '极致高效的办公 Agent' } });

    const applyBtn = screen.getByRole('button', { name: '应用补丁' });
    fireEvent.click(applyBtn);

    const patches = useInsituAnnotationStore.getState().stylePatches;
    expect(patches.length).toBe(1);
    expect(patches[0].selector).toBe('#hero-title');
    expect(patches[0].textContent).toBe('极致高效的办公 Agent');
    expect(useInsituAnnotationStore.getState().inspectionTarget).toBeNull();
  });

  it('点击取消按钮或关闭图标能直接关闭微调浮层', () => {
    render(<InSituPropertyInspector />);

    const cancelBtn = screen.getByRole('button', { name: '取消' });
    fireEvent.click(cancelBtn);

    expect(useInsituAnnotationStore.getState().inspectionTarget).toBeNull();
    expect(useInsituAnnotationStore.getState().stylePatches.length).toBe(0);
  });
});
