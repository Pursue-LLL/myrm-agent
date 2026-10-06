import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { activateOnKey } from '../a11y';

function Fixture({ onClick }: { onClick: () => void }) {
  return (
    <div role="button" tabIndex={0} onClick={onClick} onKeyDown={activateOnKey} data-testid="host">
      <input data-testid="inner-input" />
    </div>
  );
}

describe('activateOnKey', () => {
  it('Enter 触发既有 onClick', () => {
    const onClick = vi.fn();
    render(<Fixture onClick={onClick} />);

    fireEvent.keyDown(screen.getByTestId('host'), { key: 'Enter' });

    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('空格触发 onClick 并阻止页面滚动', () => {
    const onClick = vi.fn();
    render(<Fixture onClick={onClick} />);

    const notPrevented = fireEvent.keyDown(screen.getByTestId('host'), { key: ' ' });

    expect(onClick).toHaveBeenCalledTimes(1);
    expect(notPrevented).toBe(false);
  });

  it('其他按键不触发', () => {
    const onClick = vi.fn();
    render(<Fixture onClick={onClick} />);

    const notPrevented = fireEvent.keyDown(screen.getByTestId('host'), { key: 'Tab' });

    expect(onClick).not.toHaveBeenCalled();
    expect(notPrevented).toBe(true);
  });

  it.each(['ctrlKey', 'metaKey', 'altKey'] as const)('带 %s 的组合键不劫持全局快捷键', (modifier) => {
    const onClick = vi.fn();
    render(<Fixture onClick={onClick} />);

    fireEvent.keyDown(screen.getByTestId('host'), { key: 'Enter', [modifier]: true });

    expect(onClick).not.toHaveBeenCalled();
  });

  it('子元素冒泡上来的按键不被容器劫持（输入框内输入空格仍属于输入框）', () => {
    const onClick = vi.fn();
    render(<Fixture onClick={onClick} />);

    const notPrevented = fireEvent.keyDown(screen.getByTestId('inner-input'), { key: ' ' });

    expect(onClick).not.toHaveBeenCalled();
    expect(notPrevented).toBe(true);
  });
});
