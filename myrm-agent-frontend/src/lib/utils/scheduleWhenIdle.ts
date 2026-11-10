/**
 * 浏览器空闲时执行 `task`，返回取消函数。
 *
 * 没有 `requestIdleCallback` 的环境（macOS 的 WKWebView 即是）退化为 1ms 定时器，取消同样有效。
 * 依赖 `window`：服务端渲染可能触达的调用方自行判断。
 */
export function scheduleWhenIdle(task: () => void): () => void {
  if (typeof window.requestIdleCallback === 'function') {
    const handle = window.requestIdleCallback(task);
    return () => window.cancelIdleCallback(handle);
  }
  const handle = window.setTimeout(task, 1);
  return () => window.clearTimeout(handle);
}
