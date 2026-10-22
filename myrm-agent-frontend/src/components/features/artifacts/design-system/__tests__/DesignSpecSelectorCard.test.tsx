import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import { DesignSpecSelectorCard } from '../DesignSpecSelectorCard';
import { useVisualArtifactStudioStore } from '../useVisualArtifactStudioStore';

describe('DesignSpecSelectorCard', () => {
  beforeEach(() => {
    act(() => {
      useVisualArtifactStudioStore.getState().resetStudioState();
    });
  });

  it('渲染 3 套预置设计规范卡片与调色盘预览', () => {
    render(<DesignSpecSelectorCard />);

    expect(screen.getByText('DESIGN.md 工业设计系统规范')).toBeInTheDocument();
    expect(screen.getByText(/Minimal B2B/)).toBeInTheDocument();
    expect(screen.getByText(/Apple Clean/)).toBeInTheDocument();
    expect(screen.getByText(/Cyberpunk Neon/)).toBeInTheDocument();
  });

  it('点击卡片能够切换激活的规范', () => {
    render(<DesignSpecSelectorCard />);

    const appleSpecBtn = screen.getByText(/Apple Clean/).closest('button');
    expect(appleSpecBtn).not.toBeNull();

    act(() => {
      if (appleSpecBtn) {
        fireEvent.click(appleSpecBtn);
      }
    });

    expect(useVisualArtifactStudioStore.getState().activeSpec.specId).toBe('spec_apple_clean');
  });

  it('展开与折叠 DESIGN.md 规范源码查看器', () => {
    render(<DesignSpecSelectorCard />);

    const toggleBtn = screen.getByRole('button', { name: /查看 DESIGN.md/ });
    act(() => {
      fireEvent.click(toggleBtn);
    });

    expect(screen.getByText(/当前规范原稿/)).toBeInTheDocument();
    expect(screen.getByText(/Minimal B2B Design System/)).toBeInTheDocument();

    const collapseBtn = screen.getByRole('button', { name: /收起规范源码/ });
    act(() => {
      fireEvent.click(collapseBtn);
    });

    expect(screen.queryByText(/当前规范原稿/)).toBeNull();
  });
});
