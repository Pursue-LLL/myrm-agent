import React from 'react';

/**
 * 将 React children prop 转换为纯文本字符串。
 * @param children ReactNode
 * @returns 转换后的字符串
 */
export const getChildrenAsText = (children: React.ReactNode): string => {
  let text = '';
  if (Array.isArray(children)) {
    text = children.join('');
  } else if (typeof children === 'string') {
    text = children;
  } else if (children === null || children === undefined) {
    text = ''; // 处理 null 或 undefined 的情况
  } else {
    text = String(children);
  }
  // 移除末尾的单个换行符，保留内容中的换行
  return text.replace(/\n$/, '');
};
