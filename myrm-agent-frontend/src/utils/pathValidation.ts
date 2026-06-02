/**
 * 路径验证工具函数
 */

/**
 * 校验是否为绝对路径
 * @param path 待验证路径
 * @returns 是否为绝对路径（Unix: /, Windows: C:\）
 */
export const isAbsolutePath = (path: string): boolean => {
  if (!path) return false;
  // Unix 路径
  if (path.startsWith('/')) return true;
  // Windows 路径
  if (/^[A-Z]:\\/i.test(path)) return true;
  return false;
};

/**
 * 规范化路径：去除末尾斜杠
 * @param path 待规范化路径
 * @returns 规范化后的路径（保留根路径 / 和 Windows 根路径 C:\）
 */
export const normalizePath = (path: string): string => {
  if (!path) return path;
  const trimmed = path.trim();
  // 根路径不处理
  if (trimmed === '/' || /^[A-Z]:\\$/i.test(trimmed)) return trimmed;
  // 去除末尾的斜杠
  return trimmed.replace(/[/\\]+$/, '');
};
