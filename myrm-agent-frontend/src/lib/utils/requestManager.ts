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
  cancelAllRequests(): void {
    this.activeRequests.forEach((abortController) => {
      try {
        abortController.abort('页面刷新或卸载，取消请求');
      } catch {
        // 忽略已经取消的请求的错误
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

// 页面卸载时取消所有请求
if (typeof window !== 'undefined') {
  const handleBeforeUnload = () => {
    requestManager.cancelAllRequests();
  };

  const handleUnload = () => {
    requestManager.cancelAllRequests();
  };

  // 添加事件监听器
  window.addEventListener('beforeunload', handleBeforeUnload);
  window.addEventListener('unload', handleUnload);

  // 页面可见性变化时也取消请求（用户切换标签页或最小化窗口）
  const handleVisibilityChange = () => {
    if (document.hidden) {
      // 页面不可见时，延迟一小段时间再取消请求，给用户切换回来的机会
      setTimeout(() => {
        if (document.hidden) {
          requestManager.cancelAllRequests();
        }
      }, 5000); // 5秒后如果页面仍不可见，则取消请求
    }
  };

  document.addEventListener('visibilitychange', handleVisibilityChange);
}
