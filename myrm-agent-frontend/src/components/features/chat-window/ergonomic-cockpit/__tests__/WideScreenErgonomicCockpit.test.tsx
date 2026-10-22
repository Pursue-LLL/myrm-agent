import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { WideScreenErgonomicCockpit } from '../WideScreenErgonomicCockpit';
import { InBubbleGaitHUD } from '../InBubbleGaitHUD';
import { InlinePersonaAvatar } from '../InlinePersonaAvatar';
import { useErgonomicCockpitStore } from '../useErgonomicCockpitStore';

describe('WideScreenErgonomicCockpit Suite', () => {
  beforeEach(() => {
    useErgonomicCockpitStore.getState().resetState();
  });

  it('renders cockpit with header, centered main area, and side panels', () => {
    render(
      <WideScreenErgonomicCockpit>
        <div data-testid="chat-stream">沉浸式会话消息列表</div>
      </WideScreenErgonomicCockpit>
    );

    expect(screen.getByRole('region', { name: '宽屏人体工效学向心座舱' })).toBeInTheDocument();
    expect(screen.getByRole('banner', { name: '人体工效学控制面板' })).toBeInTheDocument();
    expect(screen.getByRole('main', { name: '中轴对话核心视界' })).toBeInTheDocument();
    expect(screen.getByTestId('chat-stream')).toBeInTheDocument();

    // 默认未折叠时应有左右翼面板
    expect(screen.getByLabelText('左侧智能体矩阵面板')).toBeInTheDocument();
    expect(screen.getByLabelText('右侧工件实时联动画板')).toBeInTheDocument();
  });

  it('switches viewport modes via header buttons', () => {
    render(<WideScreenErgonomicCockpit />);

    const compactBtn = screen.getByRole('button', { name: '切换至紧凑模式' });
    const standardBtn = screen.getByRole('button', { name: '切换至标准模式' });
    const ultrawideBtn = screen.getByRole('button', { name: '切换至超宽屏模式' });

    fireEvent.click(compactBtn);
    expect(useErgonomicCockpitStore.getState().viewportMode).toBe('compact');

    fireEvent.click(standardBtn);
    expect(useErgonomicCockpitStore.getState().viewportMode).toBe('standard');

    fireEvent.click(ultrawideBtn);
    expect(useErgonomicCockpitStore.getState().viewportMode).toBe('ultrawide');
  });

  it('toggles side panels for foveal centric focusing', () => {
    render(<WideScreenErgonomicCockpit />);

    const collapseBtn = screen.getByRole('button', { name: '折叠双翼聚焦中轴' });
    fireEvent.click(collapseBtn);

    // 侧栏已被折叠隐藏
    expect(screen.queryByLabelText('左侧智能体矩阵面板')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('右侧工件实时联动画板')).not.toBeInTheDocument();

    // 按钮变为展开
    const expandBtn = screen.getByRole('button', { name: '展开双翼辅助面板' });
    fireEvent.click(expandBtn);

    expect(screen.getByLabelText('左侧智能体矩阵面板')).toBeInTheDocument();
    expect(screen.getByLabelText('右侧工件实时联动画板')).toBeInTheDocument();
  });

  it('renders InBubbleGaitHUD with progress and decoupled badge', () => {
    render(<InBubbleGaitHUD />);

    expect(screen.getByRole('region', { name: '消息顶置步态仪表视窗' })).toBeInTheDocument();
    expect(screen.getByText('3/5')).toBeInTheDocument();
    expect(screen.getByText('60%')).toBeInTheDocument();
    expect(screen.getByText('Decoupled')).toBeInTheDocument();
    expect(screen.getByText('正在执行宽屏中轴视界人体工效学向心重构与步态解耦...')).toBeInTheDocument();
  });

  it('renders InlinePersonaAvatar with dynamic waveform states', () => {
    const { rerender } = render(
      <InlinePersonaAvatar state="thinking" />
    );
    expect(screen.getByTitle('正在深度推演与思考')).toBeInTheDocument();

    rerender(<InlinePersonaAvatar state="tool_executing" />);
    expect(screen.getByTitle('正在调度外部沙箱工具')).toBeInTheDocument();

    rerender(<InlinePersonaAvatar state="streaming" />);
    expect(screen.getByTitle('高帧率流式生成中')).toBeInTheDocument();
  });
});
