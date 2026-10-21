/**
 * 自适应渲染调度器
 * 替代 requestAnimationFrame 和 lodash.debounce，提供真正的基于文本长度的动态延迟防抖。
 * 彻底解耦数据接收与 UI 渲染，解决长文本流式输出时的卡顿问题。
 */
export class AdaptiveScheduler {
  private timer: NodeJS.Timeout | null = null;
  private pendingTask: (() => void) | null = null;

  /**
   * 调度一个渲染任务
   * @param task 要执行的渲染函数
   * @param textLength 当前累积的文本长度，用于动态计算延迟
   */
  schedule(task: () => void, textLength: number) {
    this.pendingTask = task;

    // 如果已经有定时器在跑，不重置它（真正的 throttle/debounce 混合模式）
    // 保证在设定的 delay 内一定会执行一次，而不是一直被推迟
    if (this.timer) {
      return;
    }

    // 动态计算延迟：短文本保持高帧率 (16ms, ~60FPS)，长文本降低帧率 (100ms, ~10FPS)
    // 这样可以大幅减轻超长 Markdown 解析对主线程的阻塞
    const delay = textLength > 2000 ? 100 : textLength > 500 ? 50 : 16;

    this.timer = setTimeout(() => {
      this.flush();
    }, delay);
  }

  /**
   * 立即执行挂起的任务并清理定时器
   */
  flush() {
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    if (this.pendingTask) {
      const task = this.pendingTask;
      this.pendingTask = null;
      task();
    }
  }

  /**
   * 取消挂起的任务和定时器（用于流中断或组件卸载，防止内存泄漏和幽灵渲染）
   */
  cancel() {
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    this.pendingTask = null;
  }
}
