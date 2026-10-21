import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { ProgressiveOnboardingGateway } from '../ProgressiveOnboardingGateway';
import { useProgressiveOnboardingStore } from '../useProgressiveOnboardingStore';

describe('ProgressiveOnboardingGateway Component Suite', () => {
  beforeEach(() => {
    useProgressiveOnboardingStore.getState().resetState();
  });

  it('renders gateway header, 5-in-1 tab navigation, chat panel, and doctor', () => {
    render(<ProgressiveOnboardingGateway />);

    expect(screen.getByLabelText('渐进式延迟配置新手引导与五合一工作台网关')).toBeInTheDocument();
    expect(screen.getByLabelText('工作台多合一导航顶栏')).toBeInTheDocument();
    expect(screen.getByText('零门槛开箱即聊与多合一工作台')).toBeInTheDocument();
    expect(screen.getByText('Zero-Config Ready')).toBeInTheDocument();

    // 五合一标签
    expect(screen.getByRole('button', { name: '切换到 对话 (Chat)' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '切换到 文件与工件 (Files)' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '切换到 高危审批 (Approvals)' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '切换到 全局搜索 (Search)' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '切换到 设置 (Settings)' })).toBeInTheDocument();

    // 默认开箱即聊面板
    expect(screen.getByText('默认通用智能体 (General Assistant)')).toBeInTheDocument();
    expect(screen.getByLabelText('一键自愈健康诊断探针')).toBeInTheDocument();
  });

  it('switches 5-in-1 workspace tabs smoothly', () => {
    render(<ProgressiveOnboardingGateway />);

    const filesBtn = screen.getByRole('button', { name: '切换到 文件与工件 (Files)' });
    fireEvent.click(filesBtn);
    expect(useProgressiveOnboardingStore.getState().activeTab).toBe('files');

    const settingsBtn = screen.getByRole('button', { name: '切换到 设置 (Settings)' });
    fireEvent.click(settingsBtn);
    expect(useProgressiveOnboardingStore.getState().activeTab).toBe('settings');
  });

  it('dispatches first chat prompt without initial blocker setup', () => {
    render(<ProgressiveOnboardingGateway />);

    const textarea = screen.getByLabelText('开箱即聊首句输入框');
    const sendBtn = screen.getByRole('button', { name: '发送首句指令' });

    fireEvent.change(textarea, { target: { value: '请帮我写一个 Python 快速排序函数' } });
    fireEvent.click(sendBtn);

    expect(useProgressiveOnboardingStore.getState().isFirstChatDispatched).toBe(true);
    expect(screen.getByText('首句指令已成功派发，3 秒内验证产品核心价值！')).toBeInTheDocument();
  });

  it('renders deferred config prompt when triggered and handles key saving', () => {
    render(<ProgressiveOnboardingGateway />);

    // 初始不应显示延迟弹卡
    expect(screen.queryByLabelText('按需延迟配置提示卡片')).not.toBeInTheDocument();

    // 触发延迟配置
    act(() => {
      useProgressiveOnboardingStore.getState().triggerDeferredConfig('沙箱运行需要接入 Claude 3.5 Sonnet');
    });

    expect(screen.getByLabelText('按需延迟配置提示卡片')).toBeInTheDocument();
    expect(screen.getByText('沙箱运行需要接入 Claude 3.5 Sonnet')).toBeInTheDocument();

    const keyInput = screen.getByLabelText('API Key 输入框');
    const saveBtn = screen.getByRole('button', { name: '保存并继续' });

    fireEvent.change(keyInput, { target: { value: 'sk-ant-test-key-999' } });
    fireEvent.click(saveBtn);

    expect(screen.getByText('已生效')).toBeInTheDocument();
  });

  it('renders provider connection failure attribution card with analogy guidance', () => {
    render(<ProgressiveOnboardingGateway />);

    expect(screen.queryByLabelText('模型测试连接失败新手归因指引卡片')).not.toBeInTheDocument();

    // 模拟连接测试抛出 401
    act(() => {
      useProgressiveOnboardingStore.getState().analyzeConnectionFailure('AuthenticationError: 401 Invalid API Key');
    });

    expect(screen.getByLabelText('模型测试连接失败新手归因指引卡片')).toBeInTheDocument();
    expect(screen.getByText('认证鉴权失败')).toBeInTheDocument();
    expect(screen.getByText('类比：钥匙无效或已过期')).toBeInTheDocument();
    expect(screen.getByText(/请检查并重新粘贴提供商控制台生成的最新有效 API Key/)).toBeInTheDocument();

    // 关闭卡片
    const closeBtn = screen.getByRole('button', { name: '关闭归因提示' });
    fireEvent.click(closeBtn);
    expect(useProgressiveOnboardingStore.getState().failureAttribution).toBeNull();
  });

  it('triggers self-healing doctor scan probe refresh', () => {
    render(<ProgressiveOnboardingGateway />);

    const rescanBtn = screen.getByRole('button', { name: '重新运行诊断探针' });
    fireEvent.click(rescanBtn);

    expect(useProgressiveOnboardingStore.getState().isDoctorScanning).toBe(true);
  });
});
