/**
 * 非原生交互元素（div / span）的键盘激活处理器，与 `role="button"` + `tabIndex={0}` 配套使用。
 *
 * 触发元素自身的原生 click，使键盘与鼠标共用同一条 `onClick` 路径：调用方无需复制激活逻辑，
 * 事件冒泡、`stopPropagation` 与 React 合成事件行为与鼠标点击完全一致。
 */
import type { KeyboardEvent } from 'react';

export function activateOnKey(event: KeyboardEvent<HTMLElement>): void {
  // 子元素（输入框、按钮等）冒泡上来的按键属于子元素自身，不能被容器劫持
  if (event.target !== event.currentTarget) {
    return;
  }
  // 带修饰键的组合键留给全局快捷键，不当作激活
  if (event.ctrlKey || event.metaKey || event.altKey) {
    return;
  }
  if (event.key !== 'Enter' && event.key !== ' ') {
    return;
  }
  // 空格的默认行为是滚动页面，需阻止
  event.preventDefault();
  event.currentTarget.click();
}
