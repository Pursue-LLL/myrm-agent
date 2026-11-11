/**
 * 全局请求管理器
 * 跟踪仍在等待响应的请求（流式请求的建立阶段、建议与标题生成），布局卸载时统一取消；
 * 响应开始后的流由各自的 AbortController 管理
 */

class RequestManager {
  private activeRequests: Set<AbortController> = new Set();

  /**
   * 注册一个新的请求
   */
  registerRequest(abortController: AbortController): void {
    this.activeRequests.add(abortController);

    // 当请求完成后自动移除
    abortController.signal.addEventListener('abort', () => {
      this.activeRequests.delete(abortController);
    });
  }

  /**
   * 注销一个请求
   */
  unregisterRequest(abortController: AbortController): void {
    this.activeRequests.delete(abortController);
  }

  /**
   * 取消所有正在进行的请求
   */
  cancelAllRequests(): void {
    this.activeRequests.forEach((abortController) => {
      try {
        if (!abortController.signal.aborted) {
          abortController.abort('Request cancelled');
        }
      } catch {
        // Ignore already-aborted controllers.
      }
    });

    this.activeRequests.clear();
  }
}

// 创建单例实例
export const requestManager = new RequestManager();
