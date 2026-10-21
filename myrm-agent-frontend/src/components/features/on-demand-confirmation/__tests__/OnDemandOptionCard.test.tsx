import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { OnDemandOptionCard } from '../OnDemandOptionCard';
import { ConfirmationOptionItem } from '../onDemandConfirmationTypes';

describe('OnDemandOptionCard 组件单测', () => {
  const sampleOption: ConfirmationOptionItem = {
    id: 'A',
    label: '深度长文调研模式',
    description: '针对复杂架构问题，生成 3000 字以上的技术分析报告',
    isRecommended: true,
    tag: '耗时约 3 分钟',
  };

  it('渲染选项卡片内容、快捷键提示与推荐标签', () => {
    const handleSelect = vi.fn();
    render(
      <OnDemandOptionCard
        option={sampleOption}
        isSelected={false}
        digitShortcut={1}
        onSelect={handleSelect}
      />
    );

    expect(screen.getByTestId('on-demand-option-card-A')).toBeInTheDocument();
    expect(screen.getByText('深度长文调研模式')).toBeInTheDocument();
    expect(screen.getByText(/针对复杂架构问题/)).toBeInTheDocument();
    expect(screen.getByText('推荐')).toBeInTheDocument();
    expect(screen.getByText('耗时约 3 分钟')).toBeInTheDocument();
    expect(screen.getByText('[1]')).toBeInTheDocument();
  });

  it('点击卡片触发 onSelect 回调并回传选项字母 ID', () => {
    const handleSelect = vi.fn();
    render(
      <OnDemandOptionCard
        option={sampleOption}
        isSelected={false}
        digitShortcut={1}
        onSelect={handleSelect}
      />
    );

    const card = screen.getByTestId('on-demand-option-card-A');
    fireEvent.click(card);

    expect(handleSelect).toHaveBeenCalledTimes(1);
    expect(handleSelect).toHaveBeenCalledWith('A');
  });

  it('选中状态具备高对比度高亮类名', () => {
    const { rerender } = render(
      <OnDemandOptionCard
        option={sampleOption}
        isSelected={false}
        digitShortcut={1}
        onSelect={vi.fn()}
      />
    );
    expect(screen.getByTestId('on-demand-option-card-A')).not.toHaveClass('ring-indigo-500/50');

    rerender(
      <OnDemandOptionCard
        option={sampleOption}
        isSelected={true}
        digitShortcut={1}
        onSelect={vi.fn()}
      />
    );
    expect(screen.getByTestId('on-demand-option-card-A')).toHaveClass('ring-indigo-500/50');
  });
});
