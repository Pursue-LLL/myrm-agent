/**
 * 输入方式可达性：让键盘与触屏用户也能触达原本只为鼠标设计的交互。
 *
 * - `activateOnKey`：非原生交互元素（div / span）的键盘激活处理器，与 `role="button"` / `role="link"` + `tabIndex={0}` 配套使用。
 *   触发元素自身的原生 click，使键盘与鼠标共用同一条 `onClick` 路径：调用方无需复制激活逻辑，
 *   事件冒泡、`stopPropagation` 与 React 合成事件行为与鼠标点击完全一致。
 * - `REVEAL_ON_HOVER`：悬停显现控件的显示契约。
 */
import type { KeyboardEvent } from 'react';

/**
 * 悬停显现控件的显示契约，配合所在容器的 `group` 使用：鼠标悬停、键盘聚焦到容器内任一元素、粗指针（触屏）、
 * 自身控制的浮层处于打开状态，四条路径任一成立即可见，否则透明。
 *
 * 为什么不是 `sm:` 之类的宽度断点：触屏没有悬停，与屏幕宽度无关——平板与横屏手机的宽度都在 `sm` 以上，
 * 宽度门控会让它们永远看不到控件；`group-hover` 在 Tailwind v4 里只在 `@media (hover: hover)` 下生效，
 * 所以必须由 `pointer-coarse` 单独兜住触屏，由 `group-focus-within` 兜住键盘。
 *
 * 为什么要有 `data-[state=open]`：Radix 的菜单 / 弹层内容渲染在 portal 里，不在 `group` 的 DOM 子树内——指针移进菜单、
 * 焦点落到菜单项后，`group-hover` 与 `group-focus-within` 同时失效，触发器会在菜单展开期间淡出，菜单像是凭空悬着；
 * 触发器在浮层打开期间带 `data-state="open"`，据此保持可见。
 *
 * 类名必须以完整字符串出现在源码里 Tailwind 才会生成样式，因此不能拆开拼接；命名组（`group/name`）
 * 无法复用本常量，需就地写带同名后缀的 `group-hover` / `group-focus-within` 与 `pointer-coarse`（控件控制浮层时再加 `data-[state=open]:opacity-100`）。
 */
export const REVEAL_ON_HOVER =
  'opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 pointer-coarse:opacity-100 data-[state=open]:opacity-100';

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
  // 链接语义只响应 Enter，空格保留给页面滚动
  if (event.key === ' ' && event.currentTarget.getAttribute('role') === 'link') {
    return;
  }
  // 按钮语义下空格的默认行为是滚动页面，需阻止
  event.preventDefault();
  event.currentTarget.click();
}
