import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { VisualBotCreatorStudioModal } from '../VisualBotCreatorStudioModal';
import { useBotCreatorStudioStore } from '../useBotCreatorStudioStore';

describe('VisualBotCreatorStudioModal', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    act(() => {
      useBotCreatorStudioStore.getState().resetStudioForm();
      useBotCreatorStudioStore.getState().closeStudio();
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders nothing when closed', () => {
    const { container } = render(<VisualBotCreatorStudioModal />);
    expect(container.firstChild).toBeNull();
  });

  it('renders complete studio modal when opened', () => {
    act(() => {
      useBotCreatorStudioStore.getState().openStudio();
    });

    render(<VisualBotCreatorStudioModal />);

    expect(screen.getByRole('dialog', { name: '智能体可视化极速新建工坊' })).toBeInTheDocument();
    expect(screen.getByText('智能体可视化极速新建工坊')).toBeInTheDocument();
    expect(screen.getByText('基本信息与人设定位')).toBeInTheDocument();
    expect(screen.getByText('一键继承主 Agent 核心资产')).toBeInTheDocument();
    expect(screen.getByText('多层次大脑认知分级推荐')).toBeInTheDocument();
    expect(screen.getByText('视觉标识与像素吉祥物')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '立即创建并激活智能体' })).toBeInTheDocument();
  });

  it('updates bot name and role inputs', () => {
    act(() => {
      useBotCreatorStudioStore.getState().openStudio();
    });

    render(<VisualBotCreatorStudioModal />);

    const nameInput = screen.getByLabelText(/智能体名称/i);
    fireEvent.change(nameInput, { target: { value: '社群增长分析师' } });

    expect(useBotCreatorStudioStore.getState().form.botName).toBe('社群增长分析师');
  });

  it('toggles master inheritance switch', () => {
    act(() => {
      useBotCreatorStudioStore.getState().openStudio();
    });

    render(<VisualBotCreatorStudioModal />);

    const switchBtn = screen.getByRole('switch', { name: '一键继承主智能体配置开关' });
    expect(switchBtn).toHaveAttribute('aria-checked', 'true');

    fireEvent.click(switchBtn);
    expect(switchBtn).toHaveAttribute('aria-checked', 'false');
    expect(useBotCreatorStudioStore.getState().form.isInheritingMaster).toBe(false);
  });

  it('switches cognitive tier and selects pixel mascot', () => {
    act(() => {
      useBotCreatorStudioStore.getState().openStudio();
    });

    render(<VisualBotCreatorStudioModal />);

    // Click on flash tier
    const flashTierButton = screen.getByText('轻量感知与分拣层 (Flash Tier)');
    fireEvent.click(flashTierButton);
    expect(useBotCreatorStudioStore.getState().form.selectedTier).toBe('fast_flash');

    // Click on shiba inu mascot
    const mascotButton = screen.getByRole('button', { name: /像素柴犬/i });
    fireEvent.click(mascotButton);
    expect(useBotCreatorStudioStore.getState().form.selectedMascotId).toBe('mascot_shiba_inu');
  });

  it('triggers AI avatar generation with timer advance', async () => {
    act(() => {
      useBotCreatorStudioStore.getState().openStudio();
    });

    render(<VisualBotCreatorStudioModal />);

    const generateBtn = screen.getByRole('button', { name: '根据人设一键生图' });
    fireEvent.click(generateBtn);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });

    expect(screen.getByText('AI 定制头像生成完毕')).toBeInTheDocument();
  });

  it('submits form to create and activate bot', async () => {
    act(() => {
      useBotCreatorStudioStore.getState().openStudio();
      useBotCreatorStudioStore.getState().updateFormField('botName', '售前专家');
    });

    render(<VisualBotCreatorStudioModal />);

    const createButton = screen.getByRole('button', { name: '立即创建并激活智能体' });
    await act(async () => {
      fireEvent.click(createButton);
    });

    expect(useBotCreatorStudioStore.getState().isOpen).toBe(false);
    expect(useBotCreatorStudioStore.getState().lastCreatedBot?.name).toBe('售前专家');
  });

  it('closes studio when cancel or close button is clicked', () => {
    act(() => {
      useBotCreatorStudioStore.getState().openStudio();
    });

    render(<VisualBotCreatorStudioModal />);

    const closeBtn = screen.getByRole('button', { name: '关闭新建工坊' });
    fireEvent.click(closeBtn);

    expect(useBotCreatorStudioStore.getState().isOpen).toBe(false);
  });
});
