import React, { useState } from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { SideTrackForkTrigger } from '../SideTrackForkTrigger';
import { SideTrackExplainerDrawer } from '../SideTrackExplainerDrawer';
import { useSideTrackStore } from '../useSideTrackStore';
import { ReadOnlyCodeSnapshot, ReadOnlyStepSnapshot } from '../sideTrackTypes';

// 模拟包含主任务流与侧边抽屉的集成容器组件
const MockMainTaskWorkspace: React.FC = () => {
  const [mainStepIndex, setMainStepIndex] = useState(1);
  const [mainTaskLogs, setMainTaskLogs] = useState<string[]>([
    '初始化数据库 Schema',
  ]);

  const activeStep: ReadOnlyStepSnapshot = {
    stepId: `step-0${mainStepIndex}`,
    stepTitle: `构建业务微服务核心代码 (第 ${mainStepIndex} 阶段)`,
    toolAction: 'compile_service',
  };

  const codeSnapshot: ReadOnlyCodeSnapshot = {
    filePath: `src/services/orderService_v${mainStepIndex}.ts`,
    codeSnippet: `export class OrderService {\n  processOrder(id: string) {\n    return true;\n  }\n}`,
    language: 'typescript',
  };

  const handleAdvanceMainTask = () => {
    setMainStepIndex((prev) => prev + 1);
    setMainTaskLogs((prev) => [...prev, `推进到第 ${mainStepIndex + 1} 阶段`]);
  };

  return (
    <div>
      <div data-testid="main-task-workspace">
        <h1>主任务工作台: 电商微服务自动化构建</h1>
        <div data-testid="main-task-step">当前步骤: {activeStep.stepTitle}</div>
        <button
          type="button"
          onClick={handleAdvanceMainTask}
          data-testid="advance-main-task-btn"
        >
          推进主任务
        </button>
        <ul>
          {mainTaskLogs.map((log, i) => (
            <li key={i}>{log}</li>
          ))}
        </ul>

        {/* 步骤旁的侧边提问触发器 */}
        <SideTrackForkTrigger
          mainSessionId="main-integration-session-001"
          mainTaskName="电商微服务自动化构建"
          activeStep={activeStep}
          codeSnapshots={[codeSnapshot]}
        />
      </div>

      {/* 侧边解释抽屉 */}
      <SideTrackExplainerDrawer />
    </div>
  );
};

describe('SideTrack Integration Suite', () => {
  beforeEach(() => {
    useSideTrackStore.getState().clearSession();
  });

  it('allows user to fork side explainer while main task runs concurrently without context pollution', () => {
    render(<MockMainTaskWorkspace />);

    expect(screen.getByTestId('main-task-workspace')).toBeInTheDocument();
    expect(
      screen.getByText('当前步骤: 构建业务微服务核心代码 (第 1 阶段)')
    ).toBeInTheDocument();

    // 1. 点击触发器，从第 1 阶段 Fork 侧边解释分支
    const forkBtn = screen.getByTestId('side-track-fork-trigger-compact');
    fireEvent.click(forkBtn);

    // 2. 抽屉打开，显示挂载的只读快照信息
    const drawer = screen.getByTestId('side-track-explainer-drawer');
    expect(drawer).toBeInTheDocument();
    expect(
      within(drawer).getByText(/构建业务微服务核心代码 \(第 1 阶段\)/)
    ).toBeInTheDocument();
    expect(within(drawer).getByText('orderService_v1.ts')).toBeInTheDocument();

    // 3. 在侧边分支发送提问
    const input = screen.getByPlaceholderText(
      '询问当前步骤设计原理、架构决策或代码实现...'
    );
    fireEvent.change(input, { target: { value: '请问该服务的并发安全性如何？' } });
    const sendBtn = screen.getByRole('button', { name: '发送提问' });
    fireEvent.click(sendBtn);

    expect(screen.getByText('请问该服务的并发安全性如何？')).toBeInTheDocument();
    expect(screen.getByText(/只读架构师分析/)).toBeInTheDocument();

    // 4. 主任务在后台独立推进，完全不受侧边问答干扰
    const advanceBtn = screen.getByTestId('advance-main-task-btn');
    fireEvent.click(advanceBtn);

    expect(
      screen.getByText('当前步骤: 构建业务微服务核心代码 (第 2 阶段)')
    ).toBeInTheDocument();
    expect(screen.getByText('推进到第 2 阶段')).toBeInTheDocument();

    // 5. 侧边分支的历史问答依旧完整存在
    expect(screen.getByText('请问该服务的并发安全性如何？')).toBeInTheDocument();

    // 6. 关闭侧边分支，主任务状态完好
    const closeBtn = screen.getByRole('button', { name: '关闭侧边解释抽屉' });
    fireEvent.click(closeBtn);
    expect(useSideTrackStore.getState().isDrawerOpen).toBe(false);
    expect(
      screen.getByText('当前步骤: 构建业务微服务核心代码 (第 2 阶段)')
    ).toBeInTheDocument();
  });
});
