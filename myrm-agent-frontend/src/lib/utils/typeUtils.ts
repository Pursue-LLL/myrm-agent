/**
 * 通用类型守卫与安全字典解构工具函数
 *
 * 防止服务端或第三方插件返回非预期类型（如 null / array / string）时，
 * 产生 TypeError 导致 React 页面白屏崩溃。
 */

/**
 * 严格检查值是否为合法非空普通对象（非 Array、非 null）
 */
export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/**
 * 安全地将任意未知值转换为纯对象字典，非法输入一律回退为空对象 {}
 */
export function asRecord(value: unknown): Record<string, unknown> {
  return isRecord(value) ? value : {};
}

/**
 * 安全获取字典中嵌套属性的值，支持链式点路径获取 (如 "metadata.usage.total_tokens")
 *
 * @param obj 源对象
 * @param path 属性路径，支持 "a.b.c" 形式
 * @param fallback 默认降级返回值
 */
export function safeGet<T = unknown>(obj: unknown, path: string, fallback?: T): T | undefined {
  if (!isRecord(obj) || !path) {
    return fallback;
  }

  const keys = path.split('.');
  let current: unknown = obj;

  for (const key of keys) {
    if (!isRecord(current)) {
      return fallback;
    }
    current = current[key];
    if (current === undefined || current === null) {
      return fallback;
    }
  }

  return (current as T) ?? fallback;
}
