import React, { useState } from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { AccessibleNavigableModelList } from '../AccessibleNavigableModelList';
import { OverflowTabStripContainer, type TabItem } from '../OverflowTabStripContainer';
import type { NavigableModelItem } from '../modelPickerKeyboardTypes';

describe('ModelPickerKeyboard & OverflowTabStrip Integration', () => {
  const initialTabs: TabItem[] = [
    { id: 'chat', label: '会话中枢' },
    { id: 'artifacts', label: '工件预览', badge: 3 },
    { id: 'settings', label: '模型与推理设定' },
  ];

  const candidateModels: NavigableModelItem[] = [
    { id: 'deepseek-v3', providerId: 'deepseek', model: 'deepseek-v3', label: 'DeepSeek V3' },
    { id: 'claude-3-7', providerId: 'anthropic', model: 'claude-3-7-sonnet', label: 'Claude 3.7 Sonnet' },
    { id: 'policy-blocked', providerId: 'legacy', model: 'legacy-v1', label: '过时废弃模型', disabled: true },
  ];

  function IntegrationFixture() {
    const [activeTab, setActiveTab] = useState('chat');
    const [selectedModel, setSelectedModel] = useState<NavigableModelItem | null>(null);
    const [isPickerOpen, setPickerOpen] = useState(true);

    return (
      <div className="w-[420px] p-4 bg-background">
        <OverflowTabStripContainer
          tabs={initialTabs}
          activeTabId={activeTab}
          onSelectTab={setActiveTab}
          trailingAction={<button type="button">操作</button>}
        />

        {isPickerOpen && (
          <div className="mt-4">
            <AccessibleNavigableModelList
              items={candidateModels}
              selectedId={selectedModel?.id}
              isOpen={isPickerOpen}
              onSelect={(item) => {
                setSelectedModel(item);
                setPickerOpen(false);
              }}
              onClose={() => setPickerOpen(false)}
            />
          </div>
        )}

        {selectedModel && (
          <div data-testid="selected-model-summary" className="mt-2 text-xs">
            已选模型: {selectedModel.label}
          </div>
        )}
      </div>
    );
  }

  it('should seamlessly orchestrate tab switching and model picker keyboard navigation', () => {
    render(<IntegrationFixture />);

    // 1. 验证标签栏正确渲染，包含右侧操作栏
    expect(screen.getByTestId('overflow-tab-strip-container')).toBeInTheDocument();
    expect(screen.getByTestId('trailing-action-slot')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /会话中枢/ })).toHaveAttribute('aria-selected', 'true');

    // 切换到最后一项标签
    const settingsTab = screen.getByRole('tab', { name: /模型与推理设定/ });
    fireEvent.click(settingsTab);
    expect(settingsTab).toHaveAttribute('aria-selected', 'true');

    // 2. 验证模型选择器列表键盘导航
    const listbox = screen.getByTestId('navigable-model-listbox');
    expect(listbox.getAttribute('aria-activedescendant')).toBe('model-opt-deepseek-v3');

    // 下移一项到 Claude 3.7
    act(() => {
      fireEvent.keyDown(listbox, { key: 'ArrowDown' });
    });
    expect(listbox.getAttribute('aria-activedescendant')).toBe('model-opt-claude-3-7');

    // 再下移，应跳过被禁用的 policy-blocked，循环回第 0 项 deepseek-v3
    act(() => {
      fireEvent.keyDown(listbox, { key: 'ArrowDown' });
    });
    expect(listbox.getAttribute('aria-activedescendant')).toBe('model-opt-deepseek-v3');

    // 再次下移到 Claude 3.7 并回车确认
    act(() => {
      fireEvent.keyDown(listbox, { key: 'ArrowDown' });
    });
    act(() => {
      fireEvent.keyDown(listbox, { key: 'Enter' });
    });

    // 3. 验证选中后列表关闭，摘要区呈现已选模型
    expect(screen.queryByTestId('accessible-navigable-model-list')).toBeNull();
    expect(screen.getByTestId('selected-model-summary')).toHaveTextContent('已选模型: Claude 3.7 Sonnet');
  });
});
