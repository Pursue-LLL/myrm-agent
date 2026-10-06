import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { activateOnKey } from '../a11y';

function Fixture({ onClick }: { onClick: () => void }) {
  return (
    // oxlint-disable-next-line jsx-a11y/prefer-tag-over-role -- 夹具刻意复现 activateOnKey 服务的非原生 role=button 宿主
    <div role="button" aria-label="host" tabIndex={0} onClick={onClick} onKeyDown={activateOnKey} data-testid="host">
      <input data-testid="inner-input" />
    </div>
  );
}

function LinkFixture({ onClick }: { onClick: () => void }) {
  return (
    // oxlint-disable-next-line jsx-a11y/prefer-tag-over-role -- 夹具刻意复现 activateOnKey 服务的非原生 role=link 宿主
    <div role="link" aria-label="link-host" tabIndex={0} onClick={onClick} onKeyDown={activateOnKey} data-testid="link">
      go
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

  it('role=link 仅响应 Enter，空格保留给页面滚动', () => {
    const onClick = vi.fn();
    render(<LinkFixture onClick={onClick} />);

    const spaceNotPrevented = fireEvent.keyDown(screen.getByTestId('link'), { key: ' ' });
    expect(onClick).not.toHaveBeenCalled();
    expect(spaceNotPrevented).toBe(true);

    fireEvent.keyDown(screen.getByTestId('link'), { key: 'Enter' });
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('子元素冒泡上来的按键不被容器劫持（输入框内输入空格仍属于输入框）', () => {
    const onClick = vi.fn();
    render(<Fixture onClick={onClick} />);

    const notPrevented = fireEvent.keyDown(screen.getByTestId('inner-input'), { key: ' ' });

    expect(onClick).not.toHaveBeenCalled();
    expect(notPrevented).toBe(true);
  });
});
