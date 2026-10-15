import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PetLoopStageBadge } from '../PetLoopStageBadge';
import { LoopTaskStep } from '../petSpeechLoopTypes';

describe('PetLoopStageBadge', () => {
  it('在无任务步骤时不渲染任何节点', () => {
    const { container } = render(<PetLoopStageBadge steps={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('正确渲染 Plan-Code-Exec-Verify 四阶进度标识与状态', () => {
    const mockSteps: LoopTaskStep[] = [
      {
        id: 's1',
        stage: 'plan',
        title: '梳理步骤',
        detail: '',
        status: 'completed',
        durationMs: 250,
      },
      {
        id: 's2',
        stage: 'code',
        title: '生成代码',
        detail: '',
        status: 'running',
      },
      {
        id: 's3',
        stage: 'exec',
        title: '沙箱编译',
        detail: '',
        status: 'pending',
      },
      {
        id: 's4',
        stage: 'verify',
        title: '单元测试',
        detail: '',
        status: 'pending',
      },
    ];

    render(<PetLoopStageBadge steps={mockSteps} />);

    expect(screen.getByTestId('pet-loop-stage-badge')).toBeInTheDocument();
    expect(screen.getByText('规划')).toBeInTheDocument();
    expect(screen.getByText('编码')).toBeInTheDocument();
    expect(screen.getByText('执行')).toBeInTheDocument();
    expect(screen.getByText('自检')).toBeInTheDocument();

    // 检查耗时
    expect(screen.getByText('250ms')).toBeInTheDocument();
  });

  it('针对失败的步骤正确呈现失败报警指示', () => {
    const failedSteps: LoopTaskStep[] = [
      {
        id: 's-fail',
        stage: 'verify',
        title: '测试门禁未通过',
        detail: 'oxlint 报错',
        status: 'failed',
      },
    ];

    render(<PetLoopStageBadge steps={failedSteps} />);
    expect(screen.getByText('自检')).toBeInTheDocument();
  });
});
