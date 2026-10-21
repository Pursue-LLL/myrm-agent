import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import { VisualArtifactStudioCard } from '../VisualArtifactStudioCard';
import { useVisualArtifactStudioStore } from '../useVisualArtifactStudioStore';

describe('VisualArtifactStudioCard', () => {
  beforeEach(() => {
    act(() => {
      useVisualArtifactStudioStore.getState().resetStudioState();
    });
  });

  it('渲染主控制台卡片、当前规范药丸与工件预览视口', () => {
    render(<VisualArtifactStudioCard />);

    expect(screen.getByText('工件设计系统与可视化审查工作台')).toBeInTheDocument();
    expect(screen.getByText(/Minimal B2B/)).toBeInTheDocument();
    expect(screen.getByTestId('artifact-preview-canvas')).toBeInTheDocument();
    expect(screen.getByText('打造下一代企业级协同智能体')).toBeInTheDocument();
    expect(screen.getByText('立即免费体验')).toBeInTheDocument();
  });

  it('点击规范配置按钮能够展开与折叠规范选择抽屉', () => {
    render(<VisualArtifactStudioCard />);

    const specToggleBtn = screen.getByRole('button', { name: /规范配置/ });
    expect(screen.queryByText('DESIGN.md 工业设计系统规范')).toBeNull();

    act(() => {
      fireEvent.click(specToggleBtn);
    });
    expect(screen.getByText('DESIGN.md 工业设计系统规范')).toBeInTheDocument();

    act(() => {
      fireEvent.click(specToggleBtn);
    });
    expect(screen.queryByText('DESIGN.md 工业设计系统规范')).toBeNull();
  });

  it('点击框选修改按钮能够切换审查模式状态', () => {
    render(<VisualArtifactStudioCard />);

    const inspectBtn = screen.getByRole('button', { name: /框选元素修改/ });
    expect(useVisualArtifactStudioStore.getState().isInspectMode).toBe(false);

    act(() => {
      fireEvent.click(inspectBtn);
    });
    expect(useVisualArtifactStudioStore.getState().isInspectMode).toBe(true);
    expect(screen.getByText('正在审查中...')).toBeInTheDocument();
  });

  it('选定元素后渲染底部回填建议 Prompt 面板并支持清空', () => {
    render(<VisualArtifactStudioCard />);

    expect(screen.queryByRole('region', { name: '所见即所得框选微调回填面板' })).toBeNull();

    act(() => {
      useVisualArtifactStudioStore.getState().selectElement({
        selectorPath: '.hero-container > button.cta-button',
        tagName: 'button',
        textContent: '立即免费体验',
        boundingBox: { x: 40, y: 100, width: 140, height: 40 },
        codeSnippet: '<button className="cta-button">立即免费体验</button>',
        generatedPromptSuggestion: '修改按钮样式',
      });
    });

    expect(
      screen.getByRole('region', { name: '所见即所得框选微调回填面板' })
    ).toBeInTheDocument();
    expect(
      screen.getByText('已锁定: .hero-container > button.cta-button')
    ).toBeInTheDocument();
    expect(screen.getByText('尺寸: 140×40px')).toBeInTheDocument();

    // 清空选择
    const clearBtn = screen.getByRole('button', { name: /清空选中/ });
    act(() => {
      fireEvent.click(clearBtn);
    });

    expect(screen.queryByRole('region', { name: '所见即所得框选微调回填面板' })).toBeNull();
  });

  it('点击一键公网发布能够唤出分享弹窗', () => {
    render(<VisualArtifactStudioCard />);

    const shareBtn = screen.getByRole('button', { name: /一键公网发布/ });
    act(() => {
      fireEvent.click(shareBtn);
    });

    expect(
      screen.getByRole('dialog', { name: '零配置一键公网发布弹窗' })
    ).toBeInTheDocument();
  });
});
