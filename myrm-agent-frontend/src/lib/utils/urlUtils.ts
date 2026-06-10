/**
 * 检查文本是否是有效的URL。
 * @param text 要检查的文本。
 * @returns 如果文本是URL，则返回true，否则返回false。
 */
export const isUrl = (text: string): boolean => {
  try {
    // 基本检查
    if (!text || typeof text !== 'string' || text.length === 0) {
      return false;
    }

    // 只检查包含 http:// 或 https:// 的文本
    if (!text.includes('http://') && !text.includes('https://')) {
      return false;
    }

    // 使用 URL 构造函数验证
    new URL(text);
    return true;
  } catch {
    return false;
  }
};

/**
 * 从URL中提取根域名。
 * @param url URL字符串。
 * @returns 根域名（例如，"google.com"）。如果解析失败，则返回原始URL。
 */
export const extractDomainFromUrl = (url: string): string => {
  try {
    // 首先检查是否真的是一个URL
    if (!isUrl(url)) {
      return url;
    }

    // 提取主机名
    const hostname = new URL(url).hostname;

    // 验证hostname是否有效
    if (!hostname || hostname.length === 0) {
      return url;
    }

    // 去除www前缀并获取根域名（一般为二级域名）
    return hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
};

/**
 * 检查URL是否可能指向一个网页，而不是特定的文件资源（如PDF, image等）。
 * @param url 要检查的URL字符串。
 * @returns 如果URL不像是指向特定文件资源，则返回true，否则返回false。
 */
export const isWebpageUrl = (url: string): boolean => {
  if (!isUrl(url)) {
    return false;
  }
  try {
    const urlObject = new URL(url);
    const pathname = urlObject.pathname;

    if (pathname.endsWith('/')) {
      return true;
    }

    const lastDotIndex = pathname.lastIndexOf('.');

    if (lastDotIndex === -1 || lastDotIndex === 0) {
      return true;
    }

    const extension = pathname.substring(lastDotIndex);
    return extension.toLowerCase() === '.html';
  } catch (e) {
    console.error(`Error parsing URL path for webpage check: ${url}`, e);
    return false;
  }
};

/**
 * 将文本分割为普通文本和@链接的数组
 */
export const splitTextWithAtLinks = (text: string): Array<{ type: 'text' | 'link'; content: string }> => {
  const atLinkRegex =
    /@(https?:\/\/[^\s]+|www\.[^\s]+|[a-zA-Z0-9]+\.(com|org|net|io|cn|co|dev|ai|app|edu|gov|mil|info|biz|tv|me|pro|xyz|top|tech|cloud|online|site|website|shop|store|blog|news|media)[^\s]*)/gi;

  const parts: Array<{ type: 'text' | 'link'; content: string }> = [];
  let lastIndex = 0;
  let match;

  while ((match = atLinkRegex.exec(text)) !== null) {
    // 添加匹配前的文本
    if (match.index > lastIndex) {
      parts.push({
        type: 'text',
        content: text.substring(lastIndex, match.index),
      });
    }

    // 添加链接（包含@符号）
    parts.push({
      type: 'link',
      content: match[0],
    });

    lastIndex = match.index + match[0].length;
  }

  // 添加剩余的文本
  if (lastIndex < text.length) {
    parts.push({
      type: 'text',
      content: text.substring(lastIndex),
    });
  }

  return parts;
};

/** Trim and strip trailing slashes from a Public Ingress base URL. */
export function normalizePublicIngressBaseUrl(raw: string): string {
  const trimmed = raw.trim();
  if (!trimmed) {
    return '';
  }
  return trimmed.replace(/\/+$/, '');
}

/** Public Ingress must be empty or HTTPS for webhook/OAuth safety. */
export function isValidPublicIngressBaseUrl(url: string): boolean {
  if (!url) {
    return true;
  }
  try {
    return new URL(url).protocol === 'https:';
  } catch {
    return false;
  }
}
