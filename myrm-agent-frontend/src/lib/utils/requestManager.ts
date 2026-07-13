/**
 * 全局请求管理器
 * 用于跟踪和取消正在进行的AI搜索流式请求
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
  cancelAllRequests(reason = 'Request cancelled'): void {
    this.activeRequests.forEach((abortController) => {
      try {
        if (!abortController.signal.aborted) {
          abortController.abort(reason);
        }
      } catch {
        // Ignore already-aborted controllers.
      }
    });

    this.activeRequests.clear();
  }

  /**
   * 获取当前活跃请求数量
   */
  getActiveRequestCount(): number {
    return this.activeRequests.size;
  }
}

// 创建单例实例
export const requestManager = new RequestManager();

// 页面卸载时取消所有请求（切换标签页不取消，避免长任务 Agent 流被误杀）
if (typeof window !== 'undefined') {
  const handleBeforeUnload = () => {
    requestManager.cancelAllRequests('Page refresh or unload');
  };

  const handleUnload = () => {
    requestManager.cancelAllRequests('Page unload');
  };

  window.addEventListener('beforeunload', handleBeforeUnload);
  window.addEventListener('unload', handleUnload);
}
