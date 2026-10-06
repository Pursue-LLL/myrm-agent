import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { SelectableCard } from '../AgentConfigSelectableCard';

const baseProps = { id: 'card-web-search', label: 'Web search', checked: false };

describe('SelectableCard 键盘可达性', () => {
  it('无内嵌控件时卡片自身是复选框，Space 与 Enter 都能切换', () => {
    const onCheckedChange = vi.fn();
    render(<SelectableCard {...baseProps} onCheckedChange={onCheckedChange} />);

    const card = screen.getByRole('checkbox', { name: /Web search/ });
    fireEvent.keyDown(card, { key: ' ' });
    fireEvent.keyDown(card, { key: 'Enter' });

    expect(onCheckedChange).toHaveBeenCalledTimes(2);
  });

  it('选中态通过 aria-checked 暴露给辅助技术', () => {
    const { rerender } = render(<SelectableCard {...baseProps} onCheckedChange={vi.fn()} />);
    expect(screen.getByRole('checkbox')).toHaveAttribute('aria-checked', 'false');

    rerender(<SelectableCard {...baseProps} checked onCheckedChange={vi.fn()} />);
    expect(screen.getByRole('checkbox')).toHaveAttribute('aria-checked', 'true');
  });

  it('禁用时不可聚焦，键盘与点击都不触发', () => {
    const onCheckedChange = vi.fn();
    render(<SelectableCard {...baseProps} disabled onCheckedChange={onCheckedChange} />);

    const card = screen.getByRole('checkbox');
    expect(card).toHaveAttribute('aria-disabled', 'true');
    expect(card).not.toHaveAttribute('tabindex');

    fireEvent.keyDown(card, { key: ' ' });
    fireEvent.click(card);
    expect(onCheckedChange).not.toHaveBeenCalled();
  });

  it('带内嵌控件时卡片不声明交互角色，内嵌控件冒泡的按键也不会被卡片劫持', () => {
    const onCheckedChange = vi.fn();
    render(
      <SelectableCard
        {...baseProps}
        onCheckedChange={onCheckedChange}
        rightElement={<button type="button">toggle</button>}
      />,
    );

    expect(screen.queryByRole('checkbox')).toBeNull();

    fireEvent.keyDown(screen.getByRole('button', { name: 'toggle' }), { key: 'Enter' });
    expect(onCheckedChange).not.toHaveBeenCalled();
  });
});
