/**
 * [INPUT]
 * - 无外部依赖（纯函数工具集）
 *
 * [OUTPUT]
 * - isAbsolutePath: 跨平台绝对路径判断
 * - normalizePath: 路径分隔符统一为正斜杠并规范化
 * - normalizeDisplayPath: Windows 盘符与正斜杠展示规范化
 * - formatPathForDisplay: 智能居中省略与前缀路径展示截断
 * - validateWorkspacePath: 工作区路径输入校验、~ 用户目录展开与非法字符防护
 *
 * [POS]
 * 全平台路径规范、工作区校验与展示截断。支持 POSIX、Windows 本地盘符与 Windows UNC 共享路径的识别、校验与安全规范化。
 */

/**
 * 校验是否为绝对路径
 * @param path 待验证路径
 * @returns 是否为绝对路径（Unix: /, Windows 盘符: C:\ 或 C:/, Windows UNC: \\server\share）
 */
export const isAbsolutePath = (path: string): boolean => {
  if (!path) {
    return false;
  }
  const trimmed = path.trim();

  // 1. Unix 路径与以正斜杠开头的 UNC 变体 (//server/share)
  if (trimmed.startsWith('/')) {
    return true;
  }

  // 2. Windows 本地盘符 (C:\ 或 C:/)
  if (/^[a-zA-Z]:[/\\]/.test(trimmed)) {
    return true;
  }

  // 3. Windows 网络共享 UNC 路径 (\\server\share)
  if (/^\\\\[^/\\]+/.test(trimmed)) {
    return true;
  }

  return false;
};

/**
 * 规范化路径：去除末尾冗余斜杠，并保留 Windows / POSIX / UNC 根路径
 * @param path 待规范化路径
 * @returns 规范化后的路径
 */
export const normalizePath = (path: string): string => {
  if (!path) {
    return path;
  }
  const trimmed = path.trim();

  // POSIX 根路径
  if (trimmed === '/') {
    return trimmed;
  }

  // Windows 本地盘符根路径 (C:\, C:/, D:\, etc.)
  if (/^[a-zA-Z]:[/\\]?$/.test(trimmed)) {
    return trimmed.endsWith('\\') || trimmed.endsWith('/') ? trimmed : `${trimmed}/`;
  }

  // Windows UNC 根共享路径 (\\server\share)
  if (/^\\\\[^/\\]+\\[^/\\]+[/\\]?$/.test(trimmed)) {
    return trimmed.replace(/[/\\]+$/, '');
  }

  // 去除末尾所有多余斜杠
  return trimmed.replace(/[/\\]+$/, '');
};

/**
 * 跨平台展示路径规范化：统一转为规范的正斜杠展示，同时规范盘符大写
 *
 * @param path 原始路径
 * @returns 适合 WebUI 与移动端展示的统一路径格式
 */
export const normalizeDisplayPath = (path: string): string => {
  if (!path) {
    return '';
  }
  let normalized = path.trim();

  // 处理 Windows UNC (\\server\share -> //server/share)
  const isUnc = /^\\\\[^/\\]+/.test(normalized) || /^\/\/[^/\\]+/.test(normalized);
  if (isUnc) {
    normalized = normalized.replace(/\\+/g, '/');
    if (!normalized.startsWith('//')) {
      normalized = '/' + normalized;
    }
    return normalizePath(normalized);
  }

  // 处理 Windows 本地盘符大写 (c:\ -> C:/)
  if (/^[a-z]:/i.test(normalized)) {
    const driveLetter = normalized[0].toUpperCase();
    normalized = `${driveLetter}:${normalized.slice(2).replace(/\\+/g, '/')}`;
    return normalizePath(normalized);
  }

  // POSIX 路径统一正斜杠
  normalized = normalized.replace(/\\+/g, '/').replace(/\/+/g, '/');
  return normalizePath(normalized);
};

/**
 * 格式化超长路径用于 UI 标签展示（居中省略）
 *
 * @param path 路径
 * @param maxLength 最大保留字符长度 (默认 36)
 */
export const formatPathForDisplay = (path: string, maxLength = 36): string => {
  const display = normalizeDisplayPath(path);
  if (!display || display.length <= maxLength) {
    return display;
  }

  const parts = display.split('/');
  if (parts.length <= 2) {
    const start = display.slice(0, Math.floor(maxLength / 2) - 2);
    const end = display.slice(-Math.floor(maxLength / 2) + 1);
    return `${start}...${end}`;
  }

  const first = parts[0] || (display.startsWith('//') ? `//${parts[2] || ''}` : '');
  const last = parts[parts.length - 1];
  const secondLast = parts[parts.length - 2];

  const candidate = `${first}/.../${secondLast}/${last}`;
  if (candidate.length <= maxLength) {
    return candidate;
  }

  return `${first}/.../${last}`.slice(0, maxLength - 3) + '...';
};

export interface WorkspacePathValidationResult {
  valid: boolean;
  normalizedPath: string;
  errorKey?: string;
}

/**
 * 验证并规范化工作区路径 (Project Directory)
 * 支持 POSIX 绝对路径、Windows 盘符、Windows UNC 以及 ~ 开头的家目录
 *
 * @param rawPath 用户输入的工作区路径
 * @returns 校验结果及规范化后的路径
 */
export const validateWorkspacePath = (rawPath: string): WorkspacePathValidationResult => {
  if (!rawPath || !rawPath.trim()) {
    return {
      valid: false,
      normalizedPath: '',
      errorKey: 'workspacePathEmpty',
    };
  }

  const trimmed = rawPath.trim();

  // 1. 检查是否存在非法控制字符（ASCII 0-31 以及 127 删除字符）
  const hasControlChars = Array.from(trimmed).some((char) => {
    const code = char.charCodeAt(0);
    return (code >= 0 && code <= 31) || code === 127;
  });
  if (hasControlChars) {
    return {
      valid: false,
      normalizedPath: '',
      errorKey: 'workspacePathInvalidChars',
    };
  }

  // 2. ~ 用户家目录路径 (例如 ~/my-project 或 ~user/project)
  if (trimmed === '~' || trimmed.startsWith('~/') || trimmed.startsWith('~\\')) {
    const displayNormalized = normalizeDisplayPath(trimmed);
    return {
      valid: true,
      normalizedPath: displayNormalized,
    };
  }

  // 3. 校验是否为绝对路径 (POSIX / Windows / UNC)
  if (!isAbsolutePath(trimmed)) {
    return {
      valid: false,
      normalizedPath: '',
      errorKey: 'workspacePathMustBeAbsolute',
    };
  }

  const displayNormalized = normalizeDisplayPath(trimmed);
  return {
    valid: true,
    normalizedPath: displayNormalized,
  };
};
