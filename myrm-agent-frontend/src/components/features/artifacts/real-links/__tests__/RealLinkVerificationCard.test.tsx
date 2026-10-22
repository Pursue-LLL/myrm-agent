import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import { RealLinkVerificationCard } from '../RealLinkVerificationCard';
import { useRealLinkAlignmentStore } from '../useRealLinkAlignmentStore';

describe('RealLinkVerificationCard', () => {
  beforeEach(() => {
    act(() => {
      useRealLinkAlignmentStore.getState().resetState();
    });
  });

  it('初始状态下渲染商用对齐率 25% 与假链警告提示条', () => {
    render(<RealLinkVerificationCard />);

    expect(
      screen.getByText('真实官方外部链接对齐与实战商用检验')
    ).toBeInTheDocument();
    expect(screen.getByText(/商用对齐率: 25%/)).toBeInTheDocument();
    expect(screen.getByTestId('placeholder-alert-banner')).toHaveTextContent(
      /检测到 3 处未商用占位假链/i
    );
    expect(screen.getByText('"立即投递校招岗位"')).toBeInTheDocument();
  });

  it('点击一键批量对齐能够将所有占位假链对齐到官方实体，对齐率升至 100%', () => {
    render(<RealLinkVerificationCard />);

    const batchBtn = screen.getByRole('button', {
      name: /一键批量对齐官方实体/,
    });
    act(() => {
      fireEvent.click(batchBtn);
    });

    expect(screen.getByText(/商用对齐率: 100%/)).toBeInTheDocument();
    expect(
      screen.getByText(/全量外链 100% 真实对齐！页面已具备开箱即用的工业级商用交付能力。/)
    ).toBeInTheDocument();
    // 批量对齐后，原先的一键批量按钮应该消失
    expect(screen.queryByRole('button', { name: /一键批量对齐官方实体/ })).toBeNull();
  });

  it('点击应用并替换到源码能够安全回写，并支持展开代码查看器', () => {
    render(<RealLinkVerificationCard />);

    // 先批量对齐
    const batchBtn = screen.getByRole('button', {
      name: /一键批量对齐官方实体/,
    });
    act(() => {
      fireEvent.click(batchBtn);
    });

    // 点击应用
    const applyBtn = screen.getByRole('button', { name: /应用并替换到源码/ });
    act(() => {
      fireEvent.click(applyBtn);
    });

    expect(screen.getByText('代码已安全生效')).toBeInTheDocument();

    // 展开代码查看器
    const toggleCodeBtn = screen.getByRole('button', {
      name: /查看对齐后的商用网页代码/,
    });
    act(() => {
      fireEvent.click(toggleCodeBtn);
    });

    expect(screen.getByText(/收起网页源码/)).toBeInTheDocument();
    expect(screen.getByText(/https:\/\/careers\.3squirrels\.com\/campus/)).toBeInTheDocument();
  });

  it('点击重置按钮能够恢复初始假链状态', () => {
    render(<RealLinkVerificationCard />);

    const batchBtn = screen.getByRole('button', {
      name: /一键批量对齐官方实体/,
    });
    act(() => {
      fireEvent.click(batchBtn);
    });
    expect(screen.getByText(/商用对齐率: 100%/)).toBeInTheDocument();

    const resetBtn = screen.getByRole('button', { name: /重置/ });
    act(() => {
      fireEvent.click(resetBtn);
    });

    expect(screen.getByText(/商用对齐率: 25%/)).toBeInTheDocument();
  });
});
