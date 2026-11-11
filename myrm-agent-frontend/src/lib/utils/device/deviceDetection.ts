/**
 * 设备检测工具
 *
 * 布局是否进入移动形态只在客户端判定：useAppLayoutState 在挂载后读取 window.innerWidth，
 * 之后监听 resize 更新，所以服务端与水合那一帧永远按宽屏布局渲染。
 * globals.css 里 `max-width: 1023px` 的窄屏兜底（主内容区左内边距、`.wide-layout-only` 外壳）
 * 与这里的断点成对，由 `__tests__/deviceDetection.test.ts` 绑定。
 *
 * 用 window.innerWidth 而不是 User-Agent：支持分屏与浏览器缩放。
 */

/** 移动端断点：窗口宽度小于此值视为移动端 */
const MOBILE_BREAKPOINT = 1024;

/**
 * 检测当前窗口宽度是否为移动端
 * 仅用于客户端 resize 事件，不应在 SSR 或初始渲染时调用
 *
 * @returns true 如果窗口宽度 < 1024px
 */
export function checkIsMobile(): boolean {
  if (typeof window === 'undefined') {
    return false;
  }
  return window.innerWidth < MOBILE_BREAKPOINT;
}
