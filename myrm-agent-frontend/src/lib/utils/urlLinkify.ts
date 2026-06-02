/**
 * URL链接化工具
 * 将纯文本中的URL转换为可点击的链接
 */

/**
 * 将文本中的URL转换为可点击的<a>标签
 */
export function linkifyUrls(text: string): string {
  const urlRegex = /(https?:\/\/[^\s)]+)/g;
  return text.replace(urlRegex, (url) => {
    return `<a href="${url}" target="_blank" rel="noopener noreferrer" class="text-blue-600 dark:text-blue-400 hover:underline">${url}</a>`;
  });
}

/**
 * 检查文本是否包含URL
 */
export function containsUrl(text: string): boolean {
  const urlRegex = /(https?:\/\/[^\s)]+)/g;
  return urlRegex.test(text);
}
