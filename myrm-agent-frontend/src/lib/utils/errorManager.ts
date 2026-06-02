/**
 * ErrorManager - 错误去重管理器
 *
 * 防止短时间内相同错误重复显示，提升用户体验
 */

import { ApiError } from '../api';

class ErrorManager {
  private errorCache = new Map<string, number>();
  private readonly DEDUP_WINDOW = 30000; // 30秒去重窗口

  /**
   * 检查是否应该显示此错误
   * @param error - API错误对象
   * @returns true表示应该显示，false表示应跳过（重复错误）
   */
  shouldShow(error: ApiError): boolean {
    // 生成错误指纹
    const fingerprint = this.generateFingerprint(error);
    const now = Date.now();
    const lastShown = this.errorCache.get(fingerprint);

    // 检查是否在去重窗口内
    if (lastShown && now - lastShown < this.DEDUP_WINDOW) {
      return false; // 重复错误，不显示
    }

    // 记录此次显示
    this.errorCache.set(fingerprint, now);

    // 清理过期缓存
    this.cleanupExpiredEntries(now);

    return true;
  }

  /**
   * 生成错误指纹
   * 基于错误码、业务码和消息生成唯一标识
   */
  private generateFingerprint(error: ApiError): string {
    const parts = [String(error.code), error.message];
    return parts.join('|');
  }

  /**
   * 清理过期的缓存条目
   */
  private cleanupExpiredEntries(now: number): void {
    for (const [key, timestamp] of this.errorCache.entries()) {
      if (now - timestamp > this.DEDUP_WINDOW) {
        this.errorCache.delete(key);
      }
    }
  }

  /**
   * 清空所有缓存（用于测试或重置）
   */
  clear(): void {
    this.errorCache.clear();
  }
}

export const errorManager = new ErrorManager();
