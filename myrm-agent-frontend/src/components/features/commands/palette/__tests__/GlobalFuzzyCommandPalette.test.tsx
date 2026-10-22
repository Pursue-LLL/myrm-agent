/** @vitest-environment jsdom */

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { GlobalFuzzyCommandPalette } from '../GlobalFuzzyCommandPalette';

const stableT = (key: string) => {
  const table: Record<string, string> = {
    title: '全局命令中枢与会话搜索',
    shortcutHint: '按 Cmd+K 随时唤起',
    inputPlaceholder: '输入指令、动作或搜索历史消息...',
    'groups.actions': '快捷控制与系统指令',
    'groups.history': '会话标题与历史消息',
    historyEmpty: '未找到匹配的历史会话',
    searchingHistory: '正在检索历史消息...',
  };
  return table[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('GlobalFuzzyCommandPalette', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders null when isOpen is false', () => {
    const { container } = render(<GlobalFuzzyCommandPalette isOpen={false} onClose={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders search input and default actions list when open', () => {
    render(<GlobalFuzzyCommandPalette isOpen={true} onClose={vi.fn()} />);

    expect(screen.getByPlaceholderText('输入指令、动作或搜索历史消息...')).toBeInTheDocument();
    expect(screen.getByText('快捷控制与系统指令')).toBeInTheDocument();
    expect(screen.getByText('Switch Active Model (/model)')).toBeInTheDocument();
    expect(screen.getByText('Switch Specialized Agent (/agent)')).toBeInTheDocument();
    expect(screen.getByText('Global Physical E-Stop (/estop)')).toBeInTheDocument();
  });

  it('filters actions based on search query', () => {
    render(<GlobalFuzzyCommandPalette isOpen={true} onClose={vi.fn()} />);

    const input = screen.getByPlaceholderText('输入指令、动作或搜索历史消息...');
    fireEvent.change(input, { target: { value: 'model' } });

    expect(screen.getByText('Switch Active Model (/model)')).toBeInTheDocument();
    expect(screen.queryByText('Global Physical E-Stop (/estop)')).not.toBeInTheDocument();
  });

  it('triggers onSelectAction when an action is clicked', () => {
    const handleSelectAction = vi.fn();
    const handleClose = vi.fn();

    render(<GlobalFuzzyCommandPalette isOpen={true} onClose={handleClose} onSelectAction={handleSelectAction} />);

    const modelAction = screen.getByText('Switch Active Model (/model)');
    fireEvent.click(modelAction);

    expect(handleSelectAction).toHaveBeenCalledTimes(1);
    expect(handleSelectAction).toHaveBeenCalledWith('switch_model');
    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it('displays debounced thread history search results', async () => {
    render(<GlobalFuzzyCommandPalette isOpen={true} onClose={vi.fn()} />);

    const input = screen.getByPlaceholderText('输入指令、动作或搜索历史消息...');
    fireEvent.change(input, { target: { value: 'Architecture' } });

    await waitFor(
      () => {
        expect(screen.getByText('会话标题与历史消息')).toBeInTheDocument();
        expect(screen.getByText(/Full-Stack Architecture RFC/i)).toBeInTheDocument();
      },
      { timeout: 1000 },
    );
  });

  it('supports keyboard navigation with Enter and Escape', () => {
    const handleSelectAction = vi.fn();
    const handleClose = vi.fn();

    render(<GlobalFuzzyCommandPalette isOpen={true} onClose={handleClose} onSelectAction={handleSelectAction} />);

    // ArrowDown moves down
    fireEvent.keyDown(window, { key: 'ArrowDown' });
    // Enter triggers selection
    fireEvent.keyDown(window, { key: 'Enter' });

    expect(handleSelectAction).toHaveBeenCalledTimes(1);

    // Escape closes palette
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(handleClose).toHaveBeenCalled();
  });
});
