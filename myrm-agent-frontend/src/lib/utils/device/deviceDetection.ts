/**
 * 设备检测工具
 *
 * 架构说明：
 * 1. 客户端直接检测 window.innerWidth（更准确）
 * 2. AppLayout 在初始化时检测，并监听 resize 事件动态更新
 * 3. PageLayout 在 SSR 时返回 null，避免 hydration mismatch
 *
 * 优势：
 * - 使用 window.innerWidth < 1024px 作为移动端判断标准
 * - 比 User-Agent 检测更准确（支持分屏、浏览器缩放等场景）
 */

/** 移动端断点：屏幕宽度小于此值视为移动端 */
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
