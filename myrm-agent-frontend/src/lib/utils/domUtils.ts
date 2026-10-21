/**
 * 检查是否滚动到接近底部位置
 */
export const isNearBottom = (threshold = 50) => {
  const scrollTop = window.scrollY;
  const scrollHeight = document.documentElement.scrollHeight;
  const clientHeight = window.innerHeight;

  return scrollHeight - scrollTop - clientHeight <= threshold;
};
